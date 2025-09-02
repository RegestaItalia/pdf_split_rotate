#!/usr/bin/env python3
"""
PDF Split Rotate - Metadata Report Generator

Generates comprehensive HTML reports with interactive visualizations from the metadata Parquet file.
This script creates detailed analytics and charts to analyze the processing results.

Features:
- Interactive Plotly visualizations
- HTML report generation
- Customer and processing analytics
- File size and distribution analysis
- Source file matching statistics
- Configurable report options
"""

import os
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any, Optional
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
import plotly.offline as pyo
from dotenv import load_dotenv

# Load environment variables
# load_dotenv(override=True)

# Configuration
METADATA_INPUT_FILE = os.getenv('REPORT_INPUT_FILE', './metadata_analysis.parquet')
REPORT_OUTPUT_FILE = os.getenv('REPORT_OUTPUT_FILE', './metadata_report.html')
REPORT_TITLE = os.getenv('REPORT_TITLE', 'PDF Split Rotate - Processing Report')
INCLUDE_DETAILED_TABLES = os.getenv('INCLUDE_DETAILED_TABLES', 'true').lower() == 'true'
MAX_CUSTOMERS_DISPLAY = int(os.getenv('MAX_CUSTOMERS_DISPLAY', '20'))
COLOR_SCHEME = os.getenv('COLOR_SCHEME', 'plotly')  # plotly, viridis, plasma, etc.

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class MetadataReportGenerator:
    """Generates comprehensive reports from metadata"""
    
    def __init__(self, input_file: str, output_file: str, title: str = "PDF Processing Report"):
        self.input_file = Path(input_file)
        self.output_file = Path(output_file)
        self.title = title
        self.df = None
        self.figures = []
        
    def load_data(self) -> bool:
        """Load metadata from Parquet file"""
        try:
            logger.info(f"Loading metadata from: {self.input_file}")
            self.df = pd.read_parquet(self.input_file)
            logger.info(f"Loaded {len(self.df)} records")
            return True
        except Exception as e:
            logger.error(f"Error loading metadata: {e}")
            return False
    
    def get_summary_stats(self) -> Dict[str, Any]:
        """Calculate summary statistics"""
        if self.df is None or self.df.empty:
            return {}
        
        stats = {
            'total_files': len(self.df),
            'total_size_gb': self.df['output_size_bytes'].sum() / (1024**3),
            'unique_customers': self.df['customer_clean'].nunique(),
            'unique_groups': self.df['group_number'].nunique(),
            'parsing_success_rate': self.df['parsing_success'].mean() * 100,
            'avg_file_size_mb': self.df['output_size_bytes'].mean() / (1024**2),
            'processing_date_range': {
                'start': self.df['analysis_timestamp'].min(),
                'end': self.df['analysis_timestamp'].max()
            }
        }
        
        # Source file statistics if available
        if 'source_file_exists' in self.df.columns:
            stats['source_match_rate'] = self.df['source_file_exists'].mean() * 100
            stats['source_files_found'] = self.df['source_file_exists'].sum()
        
        # Multi-page statistics
        if 'page_number' in self.df.columns:
            stats['multipage_files'] = self.df['page_number'].notna().sum()
            stats['singlepage_files'] = self.df['page_number'].isna().sum()
        
        return stats
    
    def create_overview_charts(self) -> List[go.Figure]:
        """Create overview charts"""
        figures = []
        
        # 1. Files by Customer (Top N)
        customer_counts = self.df['customer_clean'].value_counts().head(MAX_CUSTOMERS_DISPLAY)
        fig_customers = px.bar(
            x=customer_counts.values,
            y=customer_counts.index,
            orientation='h',
            title=f"Top {MAX_CUSTOMERS_DISPLAY} Customers by File Count",
            labels={'x': 'Number of Files', 'y': 'Customer'},
            color=customer_counts.values,
            color_continuous_scale=COLOR_SCHEME
        )
        fig_customers.update_layout(height=max(400, len(customer_counts) * 25))
        figures.append(fig_customers)
        
        # 2. File Size Distribution
        fig_size_dist = px.histogram(
            self.df,
            x='output_size_bytes',
            nbins=50,
            title='File Size Distribution',
            labels={'output_size_bytes': 'File Size (bytes)', 'count': 'Number of Files'}
        )
        fig_size_dist.update_xaxis(type='log')
        figures.append(fig_size_dist)
        
        # 3. Files by Group
        group_counts = self.df['group_number'].value_counts().sort_index()
        fig_groups = px.bar(
            x=group_counts.index,
            y=group_counts.values,
            title='Files Distribution by Group',
            labels={'x': 'Group Number', 'y': 'Number of Files'}
        )
        figures.append(fig_groups)
        
        # 4. Processing Timeline (if data spans multiple days)
        if self.df['analysis_timestamp'].dt.date.nunique() > 1:
            daily_counts = self.df.groupby(self.df['analysis_timestamp'].dt.date).size()
            fig_timeline = px.line(
                x=daily_counts.index,
                y=daily_counts.values,
                title='Processing Timeline',
                labels={'x': 'Date', 'y': 'Files Processed'}
            )
            figures.append(fig_timeline)
        
        return figures
    
    def create_detailed_analytics(self) -> List[go.Figure]:
        """Create detailed analytical charts"""
        figures = []
        
        # 1. Customer vs Group Analysis (Heatmap)
        customer_group_matrix = self.df.groupby(['customer_clean', 'group_number']).size().unstack(fill_value=0)
        
        # Limit to top customers for readability
        top_customers = self.df['customer_clean'].value_counts().head(15).index
        customer_group_matrix = customer_group_matrix.loc[top_customers]
        
        fig_heatmap = px.imshow(
            customer_group_matrix.values,
            labels=dict(x="Group Number", y="Customer", color="File Count"),
            x=customer_group_matrix.columns,
            y=customer_group_matrix.index,
            title="Customer vs Group Distribution (Heatmap)",
            color_continuous_scale=COLOR_SCHEME
        )
        figures.append(fig_heatmap)
        
        # 2. File Size by Customer (Box Plot)
        top_customers_for_box = self.df['customer_clean'].value_counts().head(10).index
        df_top_customers = self.df[self.df['customer_clean'].isin(top_customers_for_box)]
        
        fig_size_box = px.box(
            df_top_customers,
            x='customer_clean',
            y='output_size_bytes',
            title='File Size Distribution by Customer (Top 10)',
            labels={'output_size_bytes': 'File Size (bytes)', 'customer_clean': 'Customer'}
        )
        fig_size_box.update_xaxis(tickangle=45)
        fig_size_box.update_yaxis(type='log')
        figures.append(fig_size_box)
        
        # 3. Multi-page vs Single-page Analysis (if applicable)
        if 'page_number' in self.df.columns:
            page_type = self.df['page_number'].apply(lambda x: 'Multi-page' if pd.notna(x) else 'Single-page')
            page_counts = page_type.value_counts()
            
            fig_page_pie = px.pie(
                values=page_counts.values,
                names=page_counts.index,
                title='Single-page vs Multi-page Files'
            )
            figures.append(fig_page_pie)
        
        # 4. Source File Matching Analysis (if applicable)
        if 'source_file_exists' in self.df.columns:
            source_by_customer = self.df.groupby('customer_clean')['source_file_exists'].agg(['count', 'sum', 'mean']).reset_index()
            source_by_customer['match_rate'] = source_by_customer['mean'] * 100
            source_by_customer = source_by_customer.sort_values('count', ascending=False).head(15)
            
            fig_source_match = px.scatter(
                source_by_customer,
                x='count',
                y='match_rate',
                size='sum',
                hover_data=['customer_clean'],
                title='Source File Match Rate by Customer',
                labels={'count': 'Total Files', 'match_rate': 'Match Rate (%)', 'sum': 'Files Found'}
            )
            figures.append(fig_source_match)
        
        # 5. Parsing Success Analysis
        parsing_by_customer = self.df.groupby('customer_clean')['parsing_success'].agg(['count', 'mean']).reset_index()
        parsing_by_customer['success_rate'] = parsing_by_customer['mean'] * 100
        parsing_by_customer = parsing_by_customer.sort_values('count', ascending=False).head(15)
        
        fig_parsing = px.scatter(
            parsing_by_customer,
            x='count',
            y='success_rate',
            hover_data=['customer_clean'],
            title='Filename Parsing Success Rate by Customer',
            labels={'count': 'Total Files', 'success_rate': 'Success Rate (%)'}
        )
        figures.append(fig_parsing)
        
        return figures
    
    def create_summary_tables(self) -> List[str]:
        """Create summary tables as HTML"""
        tables = []
        
        # Customer Summary Table
        customer_summary = self.df.groupby('customer_clean').agg({
            'output_filename': 'count',
            'output_size_bytes': ['sum', 'mean'],
            'group_number': 'nunique',
            'parsing_success': 'mean'
        }).round(2)
        
        customer_summary.columns = ['File Count', 'Total Size (bytes)', 'Avg Size (bytes)', 'Groups Used', 'Parse Success Rate']
        customer_summary['Total Size (MB)'] = (customer_summary['Total Size (bytes)'] / (1024**2)).round(1)
        customer_summary['Avg Size (MB)'] = (customer_summary['Avg Size (bytes)'] / (1024**2)).round(1)
        customer_summary = customer_summary.drop(['Total Size (bytes)', 'Avg Size (bytes)'], axis=1)
        customer_summary = customer_summary.sort_values('File Count', ascending=False).head(20)
        
        tables.append(f"<h3>Top 20 Customers Summary</h3>{customer_summary.to_html(classes='table table-striped')}")
        
        # Group Summary Table
        group_summary = self.df.groupby('group_number').agg({
            'output_filename': 'count',
            'output_size_bytes': ['sum', 'mean'],
            'customer_clean': 'nunique'
        }).round(2)
        
        group_summary.columns = ['File Count', 'Total Size (bytes)', 'Avg Size (bytes)', 'Customers']
        group_summary['Total Size (MB)'] = (group_summary['Total Size (bytes)'] / (1024**2)).round(1)
        group_summary['Avg Size (MB)'] = (group_summary['Avg Size (bytes)'] / (1024**2)).round(1)
        group_summary = group_summary.drop(['Total Size (bytes)', 'Avg Size (bytes)'], axis=1)
        
        tables.append(f"<h3>Group Summary</h3>{group_summary.to_html(classes='table table-striped')}")
        
        # Error Summary (if any parsing errors)
        if not self.df['parsing_errors'].isna().all() and self.df['parsing_errors'].str.len().sum() > 0:
            error_summary = self.df[self.df['parsing_errors'].str.len() > 0]['parsing_errors'].value_counts().head(10)
            if not error_summary.empty:
                error_df = pd.DataFrame({'Error': error_summary.index, 'Count': error_summary.values})
                tables.append(f"<h3>Top Parsing Errors</h3>{error_df.to_html(classes='table table-striped', index=False)}")
        
        return tables
    
    def generate_html_report(self) -> bool:
        """Generate the complete HTML report"""
        try:
            logger.info("Generating overview charts...")
            overview_figures = self.create_overview_charts()
            
            logger.info("Generating detailed analytics...")
            detailed_figures = self.create_detailed_analytics()
            
            logger.info("Generating summary tables...")
            summary_tables = self.create_summary_tables() if INCLUDE_DETAILED_TABLES else []
            
            # Get summary statistics
            stats = self.get_summary_stats()
            
            # Create HTML content
            html_content = self._build_html_report(overview_figures, detailed_figures, summary_tables, stats)
            
            # Save to file
            self.output_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.output_file, 'w', encoding='utf-8') as f:
                f.write(html_content)
            
            logger.info(f"Report saved to: {self.output_file}")
            return True
            
        except Exception as e:
            logger.error(f"Error generating report: {e}")
            return False
    
    def _build_html_report(self, overview_figs: List[go.Figure], detailed_figs: List[go.Figure], 
                          tables: List[str], stats: Dict[str, Any]) -> str:
        """Build the complete HTML report"""
        
        # Convert figures to HTML
        overview_html = ""
        for i, fig in enumerate(overview_figs):
            fig_html = pyo.plot(fig, include_plotlyjs=False, output_type='div', div_id=f'overview_{i}')
            overview_html += f'<div class="chart-container">{fig_html}</div>\n'
        
        detailed_html = ""
        for i, fig in enumerate(detailed_figs):
            fig_html = pyo.plot(fig, include_plotlyjs=False, output_type='div', div_id=f'detailed_{i}')
            detailed_html += f'<div class="chart-container">{fig_html}</div>\n'
        
        # Build summary statistics HTML
        stats_html = self._build_stats_html(stats)
        
        # Combine tables
        tables_html = "\n".join(tables) if tables else ""
        
        # Complete HTML document
        html_template = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{self.title}</title>
    <script src="https://cdn.plot.ly/plotly-latest.min.js"></script>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css" rel="stylesheet">
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; }}
        .chart-container {{ margin: 20px 0; padding: 15px; border: 1px solid #ddd; border-radius: 8px; }}
        .stats-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px; margin: 20px 0; }}
        .stat-card {{ padding: 15px; background: #f8f9fa; border-radius: 8px; text-align: center; }}
        .stat-value {{ font-size: 2em; font-weight: bold; color: #007bff; }}
        .stat-label {{ font-size: 0.9em; color: #666; }}
        .section {{ margin: 30px 0; }}
        .table {{ font-size: 0.9em; }}
        h1, h2, h3 {{ color: #333; }}
        .report-header {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 30px; border-radius: 10px; text-align: center; margin-bottom: 30px; }}
    </style>
</head>
<body>
    <div class="container-fluid">
        <div class="report-header">
            <h1>{self.title}</h1>
            <p class="lead">Generated on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
        </div>
        
        <div class="section">
            <h2>📊 Summary Statistics</h2>
            {stats_html}
        </div>
        
        <div class="section">
            <h2>📈 Overview Charts</h2>
            {overview_html}
        </div>
        
        <div class="section">
            <h2>🔍 Detailed Analytics</h2>
            {detailed_html}
        </div>
        
        {f'<div class="section"><h2>📋 Summary Tables</h2>{tables_html}</div>' if tables_html else ''}
        
        <div class="section">
            <footer class="text-center text-muted">
                <p>Report generated by PDF Split Rotate - Metadata Report Generator</p>
                <p>Data source: {self.input_file.name} | Total records: {len(self.df) if self.df is not None else 0}</p>
            </footer>
        </div>
    </div>
</body>
</html>
"""
        return html_template
    
    def _build_stats_html(self, stats: Dict[str, Any]) -> str:
        """Build the statistics section HTML"""
        if not stats:
            return "<p>No statistics available</p>"
        
        stats_cards = []
        
        # Main statistics
        main_stats = [
            ('Total Files', f"{stats.get('total_files', 0):,}", '📄'),
            ('Total Size', f"{stats.get('total_size_gb', 0):.2f} GB", '💾'),
            ('Customers', f"{stats.get('unique_customers', 0):,}", '👥'),
            ('Groups', f"{stats.get('unique_groups', 0):,}", '📁'),
            ('Parse Success', f"{stats.get('parsing_success_rate', 0):.1f}%", '✅'),
            ('Avg File Size', f"{stats.get('avg_file_size_mb', 0):.1f} MB", '📏')
        ]
        
        for label, value, icon in main_stats:
            stats_cards.append(f"""
                <div class="stat-card">
                    <div class="stat-value">{icon} {value}</div>
                    <div class="stat-label">{label}</div>
                </div>
            """)
        
        # Additional stats if available
        if 'source_match_rate' in stats:
            stats_cards.append(f"""
                <div class="stat-card">
                    <div class="stat-value">🔍 {stats['source_match_rate']:.1f}%</div>
                    <div class="stat-label">Source Match Rate</div>
                </div>
            """)
        
        if 'multipage_files' in stats:
            stats_cards.append(f"""
                <div class="stat-card">
                    <div class="stat-value">📑 {stats['multipage_files']:,}</div>
                    <div class="stat-label">Multi-page Files</div>
                </div>
            """)
        
        return f'<div class="stats-grid">{"".join(stats_cards)}</div>'

def main():
    """Main execution function"""
    start_time = datetime.now()
    
    logger.info("=== PDF Split Rotate - Report Generator ===")
    logger.info(f"Input file: {METADATA_INPUT_FILE}")
    logger.info(f"Output file: {REPORT_OUTPUT_FILE}")
    logger.info(f"Report title: {REPORT_TITLE}")
    
    # Create report generator
    generator = MetadataReportGenerator(
        input_file=METADATA_INPUT_FILE,
        output_file=REPORT_OUTPUT_FILE,
        title=REPORT_TITLE
    )
    
    # Load data
    if not generator.load_data():
        logger.error("Failed to load metadata")
        return False
    
    # Generate report
    if generator.generate_html_report():
        execution_time = (datetime.now() - start_time).total_seconds()
        logger.info(f"Report generated successfully in {execution_time:.2f} seconds")
        logger.info(f"Open the report: {os.path.abspath(REPORT_OUTPUT_FILE)}")
        return True
    else:
        logger.error("Failed to generate report")
        return False

if __name__ == "__main__":
    main()
