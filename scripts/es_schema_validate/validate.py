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

# Discovery / performance knobs
SAMPLE_DOCS     = int(os.getenv("SAMPLE_DOCS", "5000"))   # docs to sample in pass 1 (0 = skip, use all in pass 2 only)
CORE_THRESHOLD  = float(os.getenv("CORE_THRESHOLD", "0.90"))  # field presence ratio to be considered 'core'
PAGE_SIZE       = int(os.getenv("PAGE_SIZE", "1000"))
QUERY_JSON      = None  # e.g., {"range": {"@timestamp": {"gte": "now-90d"}}}
TIMEOUT         = os.getenv("ES_TIMEOUT", "2m")

# Behavior flags
STRICT_MODE     = (os.getenv("STRICT_MODE", "true").lower() == "true")  # if true, ignore core detection and fingerprint all fields (presence creates new schemas)
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
    """Stream _source docs using helpers.scan."""
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
            yield hit.get("_source", {})
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
# Pass 1: discover core fields
# -----------------------------
def discover_core_fields(es, index, sample_docs, threshold, query=None):
    if STRICT_MODE:
        return set(), 0  # unused in strict mode
    if sample_docs == 0:
        # Skip discovery; core will be determined as empty -> all docs collapse to EMPTY_CORE (not useful)
        # So we recommend at least a small sample.
        print("[WARN] SAMPLE_DOCS=0; skipping core discovery. Consider setting SAMPLE_DOCS to e.g. 2000.", file=sys.stderr)
        return set(), 0

    field_counts = Counter()
    total = 0
    try:
        print(f"[DEBUG] Starting core field discovery with {sample_docs} samples...")
        for i, src in enumerate(iter_docs(es, index, query=query, page_size=PAGE_SIZE, timeout=TIMEOUT), start=1):
            seen_paths = set()
            for path, val in walk_paths(src):
                if not path:  # root non-scalar
                    continue
                seen_paths.add(path)
            for p in seen_paths:
                field_counts[p] += 1

            if i >= sample_docs:
                total = i
                break
    except Exception as e:
        print(f"[ERROR] Failed during core field discovery: {e}")
        raise
        
    if total == 0:
        print("[INFO] No documents sampled; index empty?", file=sys.stderr)
        return set(), 0

    core = {p for p, c in field_counts.items() if c / total >= threshold}
    return core, total

# -----------------------------
# Pass 2: compute schema counts
# -----------------------------
def schema_signature(src, core_fields):
    """Fingerprint based on types of *core* fields only. Missing is ignored (does not split)."""
    parts = []
    for f in core_fields:
        v = get_by_path(src, f)
        if v is None:
            continue  # missing -> ignore
        parts.append(f"{f}:{typeof(v)}")
    parts.sort()
    return "EMPTY_CORE" if not parts else "|".join(parts)

def schema_signature_strict(src):
    """Fingerprint all present fields (presence/extra fields split schemas)."""
    parts = []
    for path, val in walk_paths(src):
        if not path:
            continue
        parts.append(f"{path}:{typeof(val)}")
    parts.sort()
    return "|".join(parts) if parts else "EMPTY"

def count_schemas(es, index, core_fields, query=None):
    counts = Counter()
    total = 0
    try:
        print(f"[DEBUG] Starting schema counting for index '{index}'...")
        for src in iter_docs(es, index, query=query, page_size=PAGE_SIZE, timeout=TIMEOUT):
            sig = schema_signature_strict(src) if STRICT_MODE else schema_signature(src, core_fields)
            counts[sig] += 1
            total += 1
            if total % 1000 == 0:
                print(f"[DEBUG] Processed {total} documents...")
    except Exception as e:
        print(f"[ERROR] Failed during schema counting: {e}")
        raise
    
    print(f"[DEBUG] Completed schema counting. Total documents: {total}")
    return counts, total

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
    
    # Pass 1: discover core
    try:
        core_fields, sampled = discover_core_fields(es, INDEX_NAME, SAMPLE_DOCS, CORE_THRESHOLD, QUERY_JSON)
        if STRICT_MODE:
            print("[INFO] STRICT_MODE=true → skipping core discovery and using all present fields per doc.")
        else:
            print(f"[INFO] Sampled {sampled} docs → discovered {len(core_fields)} core fields (threshold={CORE_THRESHOLD:.2f}).")
            # Show a preview of the top 20 core fields
            preview = list(sorted(core_fields))[:20]
            if preview:
                print("[INFO] Core fields (first 20):")
                for f in preview:
                    print("  -", f)
            if not core_fields:
                print("[WARN] No core fields discovered. Consider lowering CORE_THRESHOLD or increasing SAMPLE_DOCS.", file=sys.stderr)
    except Exception as e:
        print(f"[ERROR] Failed during core field discovery: {e}")
        print(f"[ERROR] Exception type: {type(e).__name__}")
        sys.exit(1)

    # Pass 2: count schemas
    try:
        counts, total = count_schemas(es, INDEX_NAME, core_fields, QUERY_JSON)
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
        
        schema_fields = [(sig, n, pct, parse_signature(sig)) for sig, n, pct in rows]
        
        # Prepare output content
        output_lines = []
        output_lines.append("=== Schema breakdown ===")
        output_lines.append(f"Index: {INDEX_NAME} | Total docs: {total} | Mode: {'STRICT' if STRICT_MODE else 'CORE-BASED'}")
        output_lines.append(f"Generated on: {__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        output_lines.append("")
        
        # Add core fields info if not in strict mode
        if not STRICT_MODE and core_fields:
            output_lines.append(f"Core fields discovered ({len(core_fields)} total, threshold={CORE_THRESHOLD:.2f}):")
            for f in sorted(core_fields)[:50]:  # Show first 50 core fields
                output_lines.append(f"  - {f}")
            if len(core_fields) > 50:
                output_lines.append(f"  ... and {len(core_fields) - 50} more")
            output_lines.append("")
        
        # Add schema breakdown with enhanced readability
        output_lines.append("=" * 80)
        output_lines.append("SCHEMA BREAKDOWN BY FREQUENCY")
        output_lines.append("=" * 80)
        
        # Get all unique fields across all schemas for comparison
        all_fields = set()
        for _, _, _, fields in schema_fields:
            all_fields.update(fields)
        
        # Most common schema as baseline
        baseline_fields = schema_fields[0][3] if schema_fields else set()
        
        for i, (sig, n, pct, fields) in enumerate(schema_fields, start=1):
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
        for _, n, _, fields in schema_fields:
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
        
        # Output to console (simplified version)
        print("\n=== Schema breakdown ===")
        print(f"Index: {INDEX_NAME} | Total docs: {total} | Mode: {'STRICT' if STRICT_MODE else 'CORE-BASED'}")
        for i, (sig, n, pct) in enumerate(rows[:10], start=1):  # Show top 10 in console
            print(f"{i:>3}. {n:>8} docs ({pct:>6})  ->  {len(parse_signature(sig))} fields")
        if len(rows) > 10:
            print(f"     ... and {len(rows) - 10} more schemas (see detailed report)")
        
        # Save to text file in a dedicated results subfolder
        import os
        script_dir = os.path.dirname(os.path.abspath(__file__))
        results_dir = os.path.join(script_dir, "results")
        
        # Create results directory if it doesn't exist
        os.makedirs(results_dir, exist_ok=True)
        
        timestamp = __import__('datetime').datetime.now().strftime('%Y%m%d_%H%M%S')
        txt_filename = f"schema_analysis_{INDEX_NAME}_{timestamp}.txt"
        txt_filepath = os.path.join(results_dir, txt_filename)
        
        try:
            with open(txt_filepath, "w", encoding="utf-8") as f:
                f.write("\n".join(output_lines))
            print(f"\n[INFO] Detailed analysis written: {txt_filepath}")
        except Exception as e:
            print(f"[ERROR] Failed to write text file: {e}")

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
