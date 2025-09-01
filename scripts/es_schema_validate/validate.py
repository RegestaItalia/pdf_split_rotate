#!/usr/bin/env python3
"""
Schema breakdown for an Elasticsearch index, ignoring extra/missing fields.

- Index: rl_fattura
- ES >= 8.x
- Two-pass approach:
  1) Sample to discover 'core' fields (default: present in >= 90% of sampled docs)
  2) Full pass to count schema fingerprints built only from core field *types*
"""

import os
import sys
import re
import csv
from collections import Counter, defaultdict
from elasticsearch import Elasticsearch, helpers

# -----------------------------
# Configuration (edit or use env vars)
# -----------------------------
ES_URL          = os.getenv("ES_URL", "https://10.0.1.5:9200/")  # Changed to HTTPS
ES_URL_HTTP     = os.getenv("ES_URL_HTTP", "http://10.0.1.5:9200/")  # Alternative HTTP URL to try
ES_API_KEY      = os.getenv("ES_API_KEY", "UkdQbjc1Z0I2NkFTS0NQQWJ5ZDQ6QXJQY0tBcDFxdWFscVNtaUxJc3F6dw==")  # optional, else basic auth
ES_USER         = os.getenv("ES_USER", "elastic")
ES_PASS         = os.getenv("ES_PASS", "Mf_ydvioCE2EhC6yfk=9")
ES_CA_CERT      = os.getenv("ES_CA_CERT", "scripts/es_schema_validate/http_ca.crt")  # Path to CA certificate
INDEX_NAME      = os.getenv("INDEX_NAME", "rl_fattura")
KIBANA_URL      = os.getenv("KIBANA_URL", "http://10.0.1.5:5601")  # Kibana URL for document links (HTTP to avoid certificate issues)

# Discovery / performance knobs
PAGE_SIZE       = int(os.getenv("PAGE_SIZE", "1000"))
QUERY_JSON      = None  # e.g., {"range": {"@timestamp": {"gte": "now-90d"}}}
TIMEOUT         = os.getenv("ES_TIMEOUT", "2m")

# Behavior flags
STRICT_MODE     = (os.getenv("STRICT_MODE", "true").lower() == "true")  # if true, every field presence/absence creates new schemas. if false, group by structure only (ignore missing fields)
CSV_OUT         = os.getenv("CSV_OUT")  # e.g., "schemas.csv"

# -----------------------------
# Connection
# -----------------------------
def make_client(url=None, try_http_fallback=False):
    url = url or (ES_URL_HTTP if try_http_fallback else ES_URL)
    print(f"[DEBUG] Connecting to ES at: {url}")
    try:
        client_kwargs = {
            'request_timeout': 120,
            'retry_on_timeout': True,
            'max_retries': 3
        }
        
        # Handle SSL/CA certificate for HTTPS
        if url.startswith('https://'):
            import os
            if ES_CA_CERT and os.path.exists(ES_CA_CERT):
                print(f"[DEBUG] HTTPS mode: using CA certificate: {ES_CA_CERT}")
                client_kwargs['ca_certs'] = ES_CA_CERT
                client_kwargs['verify_certs'] = True
            else:
                print("[DEBUG] HTTPS mode: CA cert not found, disabling SSL verification")
                client_kwargs['verify_certs'] = False
                client_kwargs['ssl_show_warn'] = False
        
        if ES_API_KEY:
            print("[DEBUG] Using API key authentication")
            client_kwargs['api_key'] = ES_API_KEY
        elif ES_USER and ES_PASS:
            print(f"[DEBUG] Using basic auth with user: {ES_USER}")
            client_kwargs['basic_auth'] = (ES_USER, ES_PASS)
        else:
            print("[DEBUG] Using no authentication")
            
        return Elasticsearch(url, **client_kwargs)
    except Exception as e:
        print(f"[ERROR] Failed to create ES client: {e}")
        raise

def test_basic_connectivity(url):
    """Test basic HTTP connectivity without Elasticsearch client"""
    import requests
    from urllib3.exceptions import InsecureRequestWarning
    import urllib3
    
    # Disable SSL warnings for testing
    urllib3.disable_warnings(InsecureRequestWarning)
    
    try:
        print(f"[DEBUG] Testing basic HTTP connectivity to {url}")
        
        # Prepare headers and auth
        headers = {'Content-Type': 'application/json'}
        auth = None
        
        if ES_API_KEY:
            headers['Authorization'] = f'ApiKey {ES_API_KEY}'
        elif ES_USER and ES_PASS:
            auth = (ES_USER, ES_PASS)
            
        # Test basic connectivity
        response = requests.get(
            url,
            headers=headers,
            auth=auth,
            timeout=10,
            verify=False  # Disable SSL verification for testing
        )
        
        print(f"[DEBUG] HTTP Response Status: {response.status_code}")
        print(f"[DEBUG] HTTP Response Headers: {dict(response.headers)}")
        
        if response.status_code == 200:
            print(f"[DEBUG] HTTP Response Body: {response.text[:500]}...")
            return True
        else:
            print(f"[ERROR] HTTP Error: {response.status_code} - {response.text}")
            return False
            
    except Exception as e:
        print(f"[ERROR] Basic connectivity test failed: {e}")
        print(f"[ERROR] Exception type: {type(e).__name__}")
        return False

# -----------------------------
# Debug functions
# -----------------------------
def test_connection(es):
    """Test basic connection and list indices"""
    try:
        print("[DEBUG] Testing cluster connection...")
        # Test cluster health
        health = es.cluster.health()
        print(f"[DEBUG] Cluster status: {health['status']}")
        
        # List all indices
        print("[DEBUG] Fetching indices list...")
        indices = es.cat.indices(format="json")
        print(f"[DEBUG] Found {len(indices)} indices:")
        for idx in indices[:10]:  # Show first 10
            print(f"  - {idx['index']} (docs: {idx.get('docs.count', 'N/A')})")
        if len(indices) > 10:
            print(f"  ... and {len(indices) - 10} more")
            
        return True
    except Exception as e:
        print(f"[ERROR] Connection test failed: {e}")
        print(f"[ERROR] Exception type: {type(e).__name__}")
        return False

def check_index_exists(es, index_name):
    """Check if specific index exists"""
    try:
        print(f"[DEBUG] Checking if index '{index_name}' exists...")
        exists = es.indices.exists(index=index_name)
        if exists:
            # Get index info
            stats = es.indices.stats(index=index_name)
            doc_count = stats['_all']['total']['docs']['count']
            print(f"[DEBUG] Index '{index_name}' exists with {doc_count} documents")
        else:
            print(f"[ERROR] Index '{index_name}' does not exist")
            
            # Suggest similar indices
            try:
                all_indices = es.cat.indices(format="json")
                similar = [idx['index'] for idx in all_indices if index_name.lower() in idx['index'].lower()]
                if similar:
                    print(f"[SUGGESTION] Similar indices found: {', '.join(similar)}")
                else:
                    print("[SUGGESTION] No similar indices found")
            except Exception as e2:
                print(f"[ERROR] Failed to get indices for suggestions: {e2}")
        return exists
    except Exception as e:
        print(f"[ERROR] Failed to check index existence: {e}")
        print(f"[ERROR] Exception type: {type(e).__name__}")
        return False

# -----------------------------
# Utilities
# -----------------------------
def iter_docs(es, index, query=None, page_size=1000, timeout="2m"):
    """Stream docs with both _source and metadata using helpers.scan."""
    try:
        print(f"[DEBUG] Starting document iteration for index '{index}' with page_size={page_size}")
        for hit in helpers.scan(
            es,
            index=index,
            query={"query": query or {"match_all": {}}},
            size=page_size,
            preserve_order=False,
            request_timeout=120,
            scroll=timeout,
            _source=True
        ):
            # Yield both source and metadata
            yield hit.get("_source", {}), hit.get("_id"), hit.get("_index")
    except Exception as e:
        print(f"[ERROR] Failed to iterate documents from index '{index}': {e}")
        print(f"[ERROR] Exception type: {type(e).__name__}")
        if hasattr(e, 'status_code'):
            print(f"[ERROR] HTTP Status Code: {e.status_code}")
        if hasattr(e, 'error'):
            print(f"[ERROR] ES Error Details: {e.error}")
        raise

def walk_paths(src):
    """Yield (path, value) pairs for all leaf-like nodes. Arrays -> path (value is list)."""
    if src is None:
        return
    stack = [("", src)]
    while stack:
        prefix, val = stack.pop()
        if isinstance(val, dict):
            for k, v in val.items():
                key = f"{prefix}.{k}" if prefix else k
                stack.append((key, v))
        elif isinstance(val, list):
            # Treat array as a leaf at this path; element typing handled later
            yield (prefix, val)
        else:
            # Scalar leaf
            yield (prefix, val)

def typeof(value):
    """Normalize Python types to a compact schema type."""
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "long"      # closest ES numeric family-friendly name
    if isinstance(value, float):
        return "double"
    if isinstance(value, (dict,)):
        return "object"
    if isinstance(value, (list,)):
        # element type if available
        if not value or value[0] is None:
            return "array<null>"
        return f"array<{typeof(value[0])}>"
    # strings (dates often OCR’d as strings; keep as string unless you want regex coercion)
    return "string"

def get_by_path(src, path):
    cur = src
    for p in path.split("."):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(p)
        if cur is None:
            return None
    return cur

# -----------------------------
# Schema signature functions
# -----------------------------
def normalize_dict_order(obj):
    """Recursively normalize dictionary order to ensure consistent schema comparison.
    Only hierarchy matters, not field order at the same level."""
    if isinstance(obj, dict):
        # Create a new ordered dict with sorted keys
        normalized = {}
        for key in sorted(obj.keys()):
            normalized[key] = normalize_dict_order(obj[key])
        return normalized
    elif isinstance(obj, list):
        # Normalize each element in the list
        return [normalize_dict_order(item) for item in obj]
    else:
        # Return scalar values as-is
        return obj

def schema_signature_strict(src):
    """STRICT MODE: Fingerprint all present fields (presence/extra fields split schemas)."""
    # Normalize field order before generating signature
    normalized_src = normalize_dict_order(src)
    parts = []
    for path, val in walk_paths(normalized_src):
        if not path:
            continue
        parts.append(f"{path}:{typeof(val)}")
    parts.sort()
    return "|".join(parts) if parts else "EMPTY"

def schema_signature_hierarchy(src):
    """HIERARCHY MODE: Group by structure only, ignore missing fields.
    Creates a signature based on all field types present, but documents with 
    the same structure (ignoring missing fields) get the same signature."""
    # Normalize field order before generating signature
    normalized_src = normalize_dict_order(src)
    parts = []
    for path, val in walk_paths(normalized_src):
        if not path:
            continue
        parts.append(f"{path}:{typeof(val)}")
    parts.sort()
    return "|".join(parts) if parts else "EMPTY"

def count_schemas(es, index, query=None):
    counts = Counter()
    schema_docs = {}  # Store document IDs for each schema
    total = 0
    try:
        print(f"[DEBUG] Starting schema counting for index '{index}'...")
        for src, doc_id, doc_index in iter_docs(es, index, query=query, page_size=PAGE_SIZE, timeout=TIMEOUT):
            sig = schema_signature_strict(src) if STRICT_MODE else schema_signature_hierarchy(src)
            counts[sig] += 1
            
            # Store document ID for this schema
            if sig not in schema_docs:
                schema_docs[sig] = []
            schema_docs[sig].append({
                'id': doc_id,
                'index': doc_index or index,
                'preview': generate_doc_preview(src)
            })
            
            total += 1
            if total % 1000 == 0:
                print(f"[DEBUG] Processed {total} documents...")
    except Exception as e:
        print(f"[ERROR] Failed during schema counting: {e}")
        raise
    
    print(f"[DEBUG] Completed schema counting. Total documents: {total}")
    return counts, schema_docs, total

def generate_doc_preview(src):
    """Generate a short preview of the document content for display."""
    preview_fields = []
    
    # Try to find common identifying fields
    identifying_fields = [
        'RL_FATTURA.RL_FATTURA_Masterdata.Numero',
        'RL_FATTURA.RL_FATTURA_Masterdata.Data', 
        'RL_FATTURA.RL_FATTURA_Masterdata.Fornitore.Ragione_Sociale',
        'RL_FATTURA.RL_FATTURA_Masterdata.Acquirente.Ragione_Sociale',
        'RL_FATTURA.Documento-Originale.Nome_Documento'
    ]
    
    for field in identifying_fields:
        value = get_by_path(src, field)
        if value and len(preview_fields) < 3:
            field_name = field.split('.')[-1]  # Get last part of field name
            preview_fields.append(f"{field_name}: {str(value)[:50]}")
    
    # If no identifying fields found, show first few fields
    if not preview_fields:
        for path, val in walk_paths(src):
            if path and len(preview_fields) < 3:
                field_name = path.split('.')[-1]
                preview_fields.append(f"{field_name}: {str(val)[:30]}")
    
    return " | ".join(preview_fields) if preview_fields else "No preview available"

def generate_kibana_url(doc_id, index_name):
    """Generate a Kibana URL for viewing a specific document."""
    import urllib.parse
    
    # Clean the document ID: remove trailing dashes and handle special characters
    cleaned_doc_id = str(doc_id).rstrip('-').strip()
    
    # For Kibana search, we might want to escape special characters but keep it readable
    # Use quote_plus for better URL encoding or just quote specific problematic chars
    encoded_doc_id = urllib.parse.quote(cleaned_doc_id, safe='')
    
    # Use the correct dataViewId: c240470e-7d0b-4b04-9626-30ddcfee384f
    # This matches the format Kibana uses internally
    kibana_url = f"{KIBANA_URL}/app/discover#/?_g=(filters:!(),time:(from:now-30d,to:now))&_a=(columns:!(),dataSource:(dataViewId:c240470e-7d0b-4b04-9626-30ddcfee384f,type:dataView),filters:!(),interval:auto,query:(language:kuery,query:{encoded_doc_id}),sort:!())"
    
    return kibana_url

# -----------------------------
# Main
# -----------------------------
def main():
    print(f"[DEBUG] Configuration:")
    print(f"  ES_URL: {ES_URL}")
    print(f"  ES_URL_HTTP: {ES_URL_HTTP}")
    print(f"  ES_CA_CERT: {ES_CA_CERT}")
    print(f"  INDEX_NAME: {INDEX_NAME}")
    print(f"  ES_USER: {ES_USER}")
    print(f"  API_KEY set: {'Yes' if ES_API_KEY else 'No'}")
    print(f"  STRICT_MODE: {STRICT_MODE}")
    
    # First, test basic HTTP connectivity
    print("\n[DEBUG] Testing basic HTTP connectivity...")
    if test_basic_connectivity(ES_URL):
        print("[DEBUG] Basic HTTPS connectivity test passed")
        use_http_fallback = False
    else:
        print("[DEBUG] Basic HTTPS test failed, trying HTTP...")
        if test_basic_connectivity(ES_URL_HTTP):
            print("[DEBUG] Basic HTTP connectivity test passed")
            print("[INFO] Server seems to require HTTP, switching to HTTP URL")
            # We'll use HTTP for the ES client
            use_http_fallback = True
        else:
            print("[ERROR] Both HTTPS and HTTP connectivity tests failed")
            sys.exit(1)
    
    try:
        es = make_client(try_http_fallback=use_http_fallback)
        
        # Test connection first
        print("\n[DEBUG] Testing ES client connection...")
        if not test_connection(es):
            print("[ERROR] ES client connection test failed.")
            if not use_http_fallback:
                print("[DEBUG] Trying HTTP instead...")
                es = make_client(try_http_fallback=True)
                if not test_connection(es):
                    print("[ERROR] HTTP connection also failed. Cannot proceed.")
                    sys.exit(1)
            else:
                print("[ERROR] Cannot proceed.")
                sys.exit(1)
        
        # Check if index exists
        print(f"\n[DEBUG] Checking if index '{INDEX_NAME}' exists...")
        if not check_index_exists(es, INDEX_NAME):
            print(f"[ERROR] Index '{INDEX_NAME}' does not exist. Cannot proceed.")
            sys.exit(1)
            
    except Exception as e:
        print(f"[ERROR] Failed to initialize ES client or test connection: {e}")
        print(f"[ERROR] Exception type: {type(e).__name__}")
        if hasattr(e, 'status_code'):
            print(f"[ERROR] HTTP Status Code: {e.status_code}")
        sys.exit(1)
    
    # Schema analysis mode
    if STRICT_MODE:
        print("[INFO] STRICT_MODE=true → Every field presence/absence creates different schemas")
    else:
        print("[INFO] STRICT_MODE=false → Grouping by structure only, ignoring missing fields")

    # Count schemas
    try:
        counts, schema_docs, total = count_schemas(es, INDEX_NAME, QUERY_JSON)
        if total == 0:
            print("No documents found.")
            return

        # Sort by frequency
        rows = [(sig, n, f"{(n/total)*100:.2f}%") for sig, n in counts.most_common()]
        
        # Parse signatures into field sets for comparison
        def parse_signature(sig):
            if sig in ["EMPTY", "EMPTY_CORE"]:
                return set()
            return set(field.split(':')[0] for field in sig.split('|'))
        
        schema_fields = [(sig, n, pct, parse_signature(sig), schema_docs.get(sig, [])) for sig, n, pct in rows]
        
        # Prepare output content
        output_lines = []
        output_lines.append("=== Schema breakdown ===")
        output_lines.append(f"Index: {INDEX_NAME} | Total docs: {total} | Mode: {'STRICT' if STRICT_MODE else 'HIERARCHY'}")
        output_lines.append(f"Generated on: {__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        output_lines.append("")
        
        # Add run configuration
        output_lines.append("=" * 80)
        output_lines.append("RUN CONFIGURATION")
        output_lines.append("=" * 80)
        output_lines.append(f"Elasticsearch URL: {ES_URL}")
        output_lines.append(f"Index: {INDEX_NAME}")
        output_lines.append(f"Strict Mode: {STRICT_MODE}")
        output_lines.append(f"Page Size: {PAGE_SIZE}")
        output_lines.append(f"Timeout: {TIMEOUT}")
        output_lines.append(f"Query Filter: {QUERY_JSON if QUERY_JSON else 'None (all documents)'}")
        output_lines.append(f"CSV Output: {CSV_OUT if CSV_OUT else 'None'}")
        output_lines.append(f"CA Certificate: {ES_CA_CERT}")
        output_lines.append("")
        
        # Add mode info
        mode_desc = "Every field presence/absence creates different schemas" if STRICT_MODE else "Grouping by structure only, ignoring missing fields"
        output_lines.append(f"Analysis mode: {mode_desc}")
        output_lines.append("")
        
        # Add schema breakdown with enhanced readability
        output_lines.append("=" * 80)
        output_lines.append("SCHEMA BREAKDOWN BY FREQUENCY")
        output_lines.append("=" * 80)
        
        # Get all unique fields across all schemas for comparison
        all_fields = set()
        for _, _, _, fields, _ in schema_fields:
            all_fields.update(fields)
        
        # Most common schema as baseline
        baseline_fields = schema_fields[0][3] if schema_fields else set()
        
        for i, (sig, n, pct, fields, docs) in enumerate(schema_fields, start=1):
            output_lines.append("")
            output_lines.append(f"SCHEMA #{i} - {n} docs ({pct})")
            output_lines.append("-" * 60)
            
            if sig in ["EMPTY", "EMPTY_CORE"]:
                output_lines.append("  [EMPTY SCHEMA]")
                continue
            
            # Show differences from baseline (most common schema)
            if i > 1:
                missing_from_baseline = baseline_fields - fields
                extra_from_baseline = fields - baseline_fields
                
                if missing_from_baseline or extra_from_baseline:
                    output_lines.append("  Differences from most common schema:")
                    if missing_from_baseline:
                        output_lines.append(f"    MISSING ({len(missing_from_baseline)} fields):")
                        for field in sorted(missing_from_baseline):
                            output_lines.append(f"      ❌ {field}")
                    if extra_from_baseline:
                        output_lines.append(f"    EXTRA ({len(extra_from_baseline)} fields):")
                        for field in sorted(extra_from_baseline):
                            output_lines.append(f"      ➕ {field}")
                    output_lines.append("")
            
            # Show all fields grouped by hierarchy
            field_hierarchy = {}
            for field_with_type in sig.split('|'):
                field_name = field_with_type.split(':')[0]
                field_type = field_with_type.split(':')[1]
                
                # Group by top-level hierarchy
                parts = field_name.split('.')
                if len(parts) > 1:
                    top_level = parts[1] if parts[0] == 'RL_FATTURA' else parts[0]
                else:
                    top_level = 'ROOT'
                
                if top_level not in field_hierarchy:
                    field_hierarchy[top_level] = []
                field_hierarchy[top_level].append((field_name, field_type))
            
            output_lines.append(f"  Fields by hierarchy ({len(fields)} total):")
            for hierarchy in sorted(field_hierarchy.keys()):
                output_lines.append(f"    📁 {hierarchy}:")
                for field_name, field_type in sorted(field_hierarchy[hierarchy]):
                    # Simplify field name display
                    display_name = field_name.replace('RL_FATTURA.', '')
                    type_icon = "📄" if field_type == "string" else "🔢" if field_type in ["long", "double"] else "📋" if "array" in field_type else "🔸"
                    output_lines.append(f"      {type_icon} {display_name} ({field_type})")
        
        # Add summary of schema variations
        output_lines.append("")
        output_lines.append("=" * 80)
        output_lines.append("SCHEMA VARIATION SUMMARY")
        output_lines.append("=" * 80)
        
        # Analyze field frequency across all schemas
        field_frequency = {}
        for _, n, _, fields, _ in schema_fields:
            for field in fields:
                if field not in field_frequency:
                    field_frequency[field] = 0
                field_frequency[field] += n
        
        # Show fields that appear in all vs some schemas
        always_present = []
        sometimes_missing = []
        
        for field, freq in field_frequency.items():
            if freq == total:
                always_present.append(field)
            else:
                sometimes_missing.append((field, freq, f"{(freq/total)*100:.1f}%"))
        
        output_lines.append(f"Fields ALWAYS present ({len(always_present)}):")
        for field in sorted(always_present):
            display_name = field.replace('RL_FATTURA.', '')
            output_lines.append(f"  ✅ {display_name}")
        
        output_lines.append("")
        output_lines.append(f"Fields SOMETIMES missing ({len(sometimes_missing)}):")
        for field, freq, pct in sorted(sometimes_missing, key=lambda x: x[1], reverse=True):
            display_name = field.replace('RL_FATTURA.', '')
            output_lines.append(f"  ⚠️  {display_name} (present in {pct} of docs)")
        
        # Generate HTML content instead of plain text
        from html import escape as _esc
        def h(s): 
            return _esc(str(s), quote=True)

        def generate_html_report():
            html_lines = []
            
            # HTML Header with CSS for collapsible sections
            html_lines.append("""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Elasticsearch Schema Analysis Report</title>
    <style>
        body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; margin: 20px; background-color: #f5f5f5; }
        .container { max-width: 1200px; margin: 0 auto; background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
        h1 { color: #2c3e50; border-bottom: 3px solid #3498db; padding-bottom: 10px; }
        h2 { color: #34495e; margin-top: 30px; }
        h3 { color: #7f8c8d; margin-top: 20px; }
        .config-section { background-color: #ecf0f1; padding: 15px; border-radius: 5px; margin: 15px 0; }
        .config-item { margin: 5px 0; }
        .config-label { font-weight: bold; color: #2c3e50; }
        .summary-stats { display: flex; gap: 20px; margin: 20px 0; }
        .stat-card { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 15px; border-radius: 8px; text-align: center; flex: 1; }
        .stat-number { font-size: 2em; font-weight: bold; }
        .stat-label { font-size: 0.9em; opacity: 0.9; }
        
        /* Collapsible sections */
        .collapsible { background-color: #34495e; color: white; cursor: pointer; padding: 15px; border: none; text-align: left; outline: none; font-size: 16px; width: 100%; border-radius: 4px; margin: 5px 0; transition: 0.3s; }
        .collapsible:hover { background-color: #2c3e50; }
        .collapsible.active { background-color: #3498db; }
        .collapsible:after { content: '\\002B'; color: white; font-weight: bold; float: right; margin-left: 5px; }
        .collapsible.active:after { content: "\\2212"; }
        .content { padding: 0 18px; background-color: #f8f9fa; max-height: 0; overflow: hidden; transition: max-height 0.2s ease-out; border-radius: 0 0 4px 4px; }
        .content.active { max-height: 80vh; padding: 18px; overflow-y: auto; }
        
        /* Schema styling */
        .schema-item { margin: 20px 0; border: 1px solid #bdc3c7; border-radius: 8px; overflow: hidden; }
        .schema-header { background: linear-gradient(90deg, #3498db, #2980b9); color: white; padding: 15px; cursor: pointer; }
        .schema-header:hover { background: linear-gradient(90deg, #2980b9, #2c3e50); }
        .schema-content { padding: 20px; background: white; }
        .field-hierarchy { margin: 10px 0; }
        .hierarchy-group { margin: 15px 0; border-left: 3px solid #3498db; padding-left: 15px; }
        .hierarchy-title { font-weight: bold; color: #2c3e50; margin-bottom: 10px; }
        .field-item { padding: 5px 10px; margin: 2px 0; background-color: #ecf0f1; border-radius: 4px; font-family: monospace; }
        .field-type-string { border-left: 4px solid #e74c3c; }
        .field-type-number { border-left: 4px solid #f39c12; }
        .field-type-array { border-left: 4px solid #9b59b6; }
        .field-type-object { border-left: 4px solid #27ae60; }
        .field-type-other { border-left: 4px solid #95a5a6; }
        
        /* Document list styling */
        .doc-section { margin: 15px 0; }
        .doc-toggle { background-color: #27ae60; color: white; border: none; padding: 10px 15px; border-radius: 5px; cursor: pointer; font-size: 14px; transition: 0.3s; }
        .doc-toggle:hover { background-color: #229954; }
        .doc-list { margin-top: 10px; }
        
        /* Differences styling */
        .diff-missing { color: #e74c3c; font-weight: bold; }
        .diff-extra { color: #27ae60; font-weight: bold; }
        .always-present { color: #27ae60; }
        .sometimes-missing { color: #f39c12; }
        
        /* Responsive */
        @media (max-width: 768px) {
            .summary-stats { flex-direction: column; }
            .container { margin: 10px; padding: 15px; }
        }
    </style>
</head>
<body>
    <div class="container">""")
            
            # Title and basic info
            html_lines.append(f"<h1>📊 Elasticsearch Schema Analysis Report</h1>")
            html_lines.append(f"<p><strong>Index:</strong> {INDEX_NAME} | <strong>Total Documents:</strong> {total:,} | <strong>Mode:</strong> {'STRICT' if STRICT_MODE else 'HIERARCHY'}</p>")
            html_lines.append(f"<p><strong>Generated:</strong> {__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>")
            
            # Summary statistics
            html_lines.append('<div class="summary-stats">')
            html_lines.append(f'<div class="stat-card"><div class="stat-number">{len(rows)}</div><div class="stat-label">Unique Schemas</div></div>')
            html_lines.append(f'<div class="stat-card"><div class="stat-number">{len(all_fields)}</div><div class="stat-label">Total Fields</div></div>')
            html_lines.append(f'<div class="stat-card"><div class="stat-number">{len(always_present)}</div><div class="stat-label">Always Present Fields</div></div>')
            html_lines.append(f'<div class="stat-card"><div class="stat-number">{len(sometimes_missing)}</div><div class="stat-label">Sometimes Missing Fields</div></div>')
            html_lines.append('</div>')
            
            # Configuration section (collapsible)
            html_lines.append('<button class="collapsible">🔧 Run Configuration</button>')
            html_lines.append('<div class="content">')
            html_lines.append('<div class="config-section">')
            html_lines.append(f'<div class="config-item"><span class="config-label">Elasticsearch URL:</span> {ES_URL}</div>')
            html_lines.append(f'<div class="config-item"><span class="config-label">Index:</span> {INDEX_NAME}</div>')
            html_lines.append(f'<div class="config-item"><span class="config-label">Strict Mode:</span> {STRICT_MODE}</div>')
            html_lines.append(f'<div class="config-item"><span class="config-label">Analysis Mode:</span> {"Every field presence/absence creates different schemas" if STRICT_MODE else "Grouping by structure only, ignoring missing fields"}</div>')
            html_lines.append(f'<div class="config-item"><span class="config-label">Page Size:</span> {PAGE_SIZE}</div>')
            html_lines.append(f'<div class="config-item"><span class="config-label">Timeout:</span> {TIMEOUT}</div>')
            html_lines.append(f'<div class="config-item"><span class="config-label">Query Filter:</span> {QUERY_JSON if QUERY_JSON else "None (all documents)"}</div>')
            html_lines.append(f'<div class="config-item"><span class="config-label">CSV Output:</span> {CSV_OUT if CSV_OUT else "None"}</div>')
            html_lines.append('</div></div>')
            
            # Field presence analysis (collapsible)
            html_lines.append('<button class="collapsible">📈 Field Presence Analysis</button>')
            html_lines.append('<div class="content">')
            html_lines.append('<h3>Fields Always Present</h3>')
            if always_present:
                for field in sorted(always_present):
                    display_name = field.replace('RL_FATTURA.', '')
                    html_lines.append(f'<div class="field-item always-present">✅ {display_name}</div>')
            else:
                html_lines.append('<p>No fields are present in all documents.</p>')
            
            html_lines.append('<h3>Fields Sometimes Missing</h3>')
            if sometimes_missing:
                for field, freq, pct in sorted(sometimes_missing, key=lambda x: x[1], reverse=True):
                    display_name = field.replace('RL_FATTURA.', '')
                    html_lines.append(f'<div class="field-item sometimes-missing">⚠️ {display_name} (present in {pct} of docs)</div>')
            else:
                html_lines.append('<p>All fields are consistently present.</p>')
            html_lines.append('</div>')
            
            # Schema breakdown - main collapsible section
            html_lines.append('<button class="collapsible">🔍 Schema Breakdown by Frequency</button>')
            html_lines.append('<div class="content">')
            
            for i, (sig, n, pct, fields, docs) in enumerate(schema_fields, start=1):
                # === Schema item wrapper ===
                html_lines.append('<div class="schema-item">')

                # Header (clickable)
                html_lines.append(
                    f'<div class="schema-header" onclick="toggleSchema({i})">'
                    f'<strong>{h("Schema #"+str(i))}</strong> - {h(f"{n:,}")} documents ({h(pct)}) - {h(len(fields))} fields'
                    f'</div>'
                )

                # Content container (initially hidden)
                html_lines.append(f'<div id="schema-{i}" class="schema-content" style="display: none;">')

                if sig in ["EMPTY", "EMPTY_CORE"]:
                    html_lines.append('<p><em>Empty schema - no fields present</em></p>')
                else:
                    # --- Differences from baseline (schema #1) ---
                    if i > 1:
                        missing_from_baseline = baseline_fields - fields
                        extra_from_baseline   = fields - baseline_fields

                        if missing_from_baseline or extra_from_baseline:
                            html_lines.append('<h4>Differences from Most Common Schema:</h4>')
                            if missing_from_baseline:
                                html_lines.append(f'<p><strong class="diff-missing">Missing ({len(missing_from_baseline)} fields):</strong></p>')
                                for field in sorted(missing_from_baseline):
                                    display_name = field.replace('RL_FATTURA.', '')
                                    html_lines.append(f'<div class="field-item diff-missing">❌ {h(display_name)}</div>')
                            if extra_from_baseline:
                                html_lines.append(f'<p><strong class="diff-extra">Extra ({len(extra_from_baseline)} fields):</strong></p>')
                                for field in sorted(extra_from_baseline):
                                    display_name = field.replace('RL_FATTURA.', '')
                                    html_lines.append(f'<div class="field-item diff-extra">➕ {h(display_name)}</div>')

                    # --- Fields by hierarchy ---
                    field_hierarchy = {}
                    for field_with_type in sig.split('|'):
                        if ':' not in field_with_type:
                            continue
                        field_name, field_type = field_with_type.split(':', 1)  # keep right side intact

                        parts = field_name.split('.')
                        top_level = (parts[1] if parts and parts[0] == 'RL_FATTURA' and len(parts) > 1 else parts[0]) if parts else 'ROOT'
                        field_hierarchy.setdefault(top_level, []).append((field_name, field_type))

                    html_lines.append('<h4>Fields by Hierarchy:</h4>')
                    for hierarchy in sorted(field_hierarchy.keys()):
                        html_lines.append('<div class="hierarchy-group">')
                        html_lines.append(f'<div class="hierarchy-title">📁 {h(hierarchy)}</div>')
                        for field_name, field_type in sorted(field_hierarchy[hierarchy]):
                            display_name = field_name.replace('RL_FATTURA.', '')
                            # stable class name
                            type_class = ("string" if field_type == "string"
                                        else "number" if field_type in ("long", "double")
                                        else "array" if "array" in field_type
                                        else "object" if field_type == "object"
                                        else "other")
                            type_icon = ("📄" if field_type == "string"
                                        else "🔢" if field_type in ("long", "double")
                                        else "📋" if "array" in field_type
                                        else "🔸")
                            html_lines.append(
                                f'<div class="field-item field-type-{type_class}">'
                                f'{type_icon} {h(display_name)} <code>({h(field_type)})</code></div>'
                            )
                        html_lines.append('</div>')  # close .hierarchy-group

                    # --- Documents list (optional) ---
                    if docs:
                        html_lines.append('<h4>Documents with this Schema:</h4>')
                        html_lines.append('<div class="doc-section">')
                        html_lines.append(f'<button class="doc-toggle" onclick="toggleDocs({i})">📄 Show/Hide {h(len(docs))} Documents</button>')
                        html_lines.append(
                            f'<div id="docs-{i}" class="doc-list" '
                            'style="display: none; max-height: 300px; overflow-y: auto; '
                            'border: 1px solid #ddd; padding: 10px; border-radius: 4px; margin-top: 10px;">'
                        )

                        for doc_data in docs[:50]:
                            doc_id      = doc_data.get('id', '')
                            doc_index   = doc_data.get('index', INDEX_NAME)
                            doc_preview = doc_data.get('preview', '')
                            kibana_url  = generate_kibana_url(doc_id, doc_index)

                            html_lines.append(
                                '<div style="margin: 5px 0; padding: 8px; background-color: #f8f9fa; '
                                'border-radius: 4px; border-left: 3px solid #3498db;">'
                            )
                            html_lines.append(
                                f'<a href="{h(kibana_url)}" target="_blank" '
                                'style="text-decoration: none; color: #2c3e50; font-family: monospace;">'
                                f'🔗 {h(doc_id)}</a>'
                            )
                            html_lines.append(f'<div style="font-size: 0.9em; color: #666; margin-top: 4px;">{h(doc_preview)}</div>')
                            html_lines.append('</div>')  # close doc card

                        if len(docs) > 50:
                            html_lines.append(
                                '<div style="margin: 10px 0; padding: 8px; background-color: #fff3cd; '
                                'border-radius: 4px; color: #856404;">'
                                f'⚠️ Showing first 50 of {h(len(docs))} documents'
                                '</div>'
                            )

                        html_lines.append('</div>')  # close #docs-{i}
                        html_lines.append('</div>')  # close .doc-section

                # Close content + item (exactly one each)
                html_lines.append('</div>')  # close .schema-content
                html_lines.append('</div>')  # close .schema-item
            
            # JavaScript for interactivity
            html_lines.append("""
    </div>
    <script>
        // Collapsible sections
        var coll = document.getElementsByClassName("collapsible");
        for (var i = 0; i < coll.length; i++) {
            coll[i].addEventListener("click", function() {
                this.classList.toggle("active");
                var content = this.nextElementSibling;
                content.classList.toggle("active");
            });
        }
        
        // Schema toggle
        function toggleSchema(id) {
            var content = document.getElementById("schema-" + id);
            if (content.style.display === "none") {
                content.style.display = "block";
            } else {
                content.style.display = "none";
            }
        }
        
        // Document list toggle
        function toggleDocs(id) {
            var content = document.getElementById("docs-" + id);
            if (content.style.display === "none") {
                content.style.display = "block";
            } else {
                content.style.display = "none";
            }
        }
        
        // Auto-expand first few schemas
        for (var i = 1; i <= Math.min(3, """ + str(len(schema_fields)) + """); i++) {
            toggleSchema(i);
        }
        
        // Auto-expand configuration
        document.getElementsByClassName("collapsible")[0].click();
    </script>
</body>
</html>""")
            
            return '\n'.join(html_lines)
        
        html_content = generate_html_report()
        
        # Output to console (simplified version)
        print("\n=== Schema breakdown ===")
        print(f"Index: {INDEX_NAME} | Total docs: {total} | Mode: {'STRICT' if STRICT_MODE else 'HIERARCHY'}")
        for i, (sig, n, pct) in enumerate(rows[:10], start=1):  # Show top 10 in console
            print(f"{i:>3}. {n:>8} docs ({pct:>6})  ->  {len(parse_signature(sig))} fields")
        if len(rows) > 10:
            print(f"     ... and {len(rows) - 10} more schemas (see detailed HTML report)")
        
        # Save to HTML file in a dedicated results subfolder
        import os
        script_dir = os.path.dirname(os.path.abspath(__file__))
        results_dir = os.path.join(script_dir, "results")
        
        # Create results directory if it doesn't exist
        os.makedirs(results_dir, exist_ok=True)
        
        timestamp = __import__('datetime').datetime.now().strftime('%Y%m%d_%H%M%S')
        html_filename = f"schema_analysis_{INDEX_NAME}_{timestamp}.html"
        html_filepath = os.path.join(results_dir, html_filename)
        
        try:
            with open(html_filepath, "w", encoding="utf-8") as f:
                f.write(html_content)
            print(f"\n[INFO] Interactive HTML report written: {html_filepath}")
        except Exception as e:
            print(f"[ERROR] Failed to write HTML file: {e}")

        # Optional CSV
        if CSV_OUT:
            with open(CSV_OUT, "w", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                w.writerow(["rank", "docs", "percent", "schema_signature"])
                for i, (sig, n, pct) in enumerate(rows, start=1):
                    w.writerow([i, n, pct, sig])
            print(f"\n[INFO] CSV written: {CSV_OUT}")
            
    except Exception as e:
        print(f"[ERROR] Failed during schema counting: {e}")
        print(f"[ERROR] Exception type: {type(e).__name__}")
        if hasattr(e, 'status_code'):
            print(f"[ERROR] HTTP Status Code: {e.status_code}")
        sys.exit(1)

if __name__ == "__main__":
    main()
