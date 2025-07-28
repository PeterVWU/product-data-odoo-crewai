import pandas as pd
import json
from pathlib import Path
from crewai.tools import tool
from typing import Dict, Any


def _detect_column_mapping(columns: list) -> Dict[str, str]:
    """Detect column mapping based on common patterns."""
    column_map = {}
    
    # Define mapping patterns (case insensitive)
    patterns = {
        'sku': ['internal reference', 'sku', 'item code', 'product code', 'reference'],
        'name': ['product name', 'name', 'title', 'product title', 'description'],
        'qty': ['on hand', 'qty', 'quantity', 'stock', 'inventory'],
        'price': ['sales price', 'price', 'unit price', 'cost', 'sale price'],
        'category': ['odoo category', 'category', 'product category', 'type']
    }
    
    for col in columns:
        col_lower = col.lower().strip()
        for std_name, possible_names in patterns.items():
            if any(pattern in col_lower for pattern in possible_names):
                column_map[col] = std_name
                break
    
    return column_map


def _validate_data(df: pd.DataFrame) -> Dict[str, Any]:
    """Basic data validation."""
    validation = {}
    
    # Check for missing values
    validation['missing_values'] = df.isnull().sum().to_dict()
    
    # Check data types
    try:
        # Try to convert qty to numeric
        pd.to_numeric(df['qty'], errors='raise')
        validation['qty_valid'] = True
    except:
        validation['qty_valid'] = False
        
    try:
        # Try to convert price to numeric
        pd.to_numeric(df['price'], errors='raise')
        validation['price_valid'] = True
    except:
        validation['price_valid'] = False
    
    # Check for duplicates
    validation['duplicate_skus'] = df['sku'].duplicated().sum()
    
    return validation


@tool
def csv_processor_tool(csv_path: str, out_dir: str, encoding: str = "utf-8") -> Dict[str, Any]:
    """
    Lightweight tool to process CSV files with column mapping and basic validation.
    Maps vendor columns to standard names (sku, name, qty, price, category) and
    outputs cleaned CSV with summary statistics.
    
    Args:
        csv_path: Path to input CSV file
        out_dir: Output directory for cleaned CSV
        encoding: File encoding (default: utf-8)
        
    Returns:
        Dict with status, summary stats, and output paths
    """
    try:
        # Ensure output directory exists
        out_path = Path(out_dir)
        out_path.mkdir(parents=True, exist_ok=True)
        
        # Read CSV
        df = pd.read_csv(csv_path, encoding=encoding)
        
        # Column mapping - map common vendor columns to standard names
        column_map = _detect_column_mapping(df.columns.tolist())
        
        # Check if we found all required columns
        required_cols = ['sku', 'name', 'qty', 'price', 'category']
        missing_cols = [col for col in required_cols if col not in column_map.values()]
        
        if missing_cols:
            return {
                "status": "failed",
                "error": f"Could not map required columns: {missing_cols}",
                "detected_columns": df.columns.tolist()
            }
        
        # Create cleaned dataframe with standard column names
        cleaned_df = pd.DataFrame()
        reverse_map = {v: k for k, v in column_map.items()}
        
        for std_col in required_cols:
            original_col = reverse_map[std_col]
            cleaned_df[std_col] = df[original_col]
        
        # Basic validation
        validation_results = _validate_data(cleaned_df)
        
        # Save cleaned CSV
        output_file = out_path / "cleaned_products.csv"
        cleaned_df.to_csv(output_file, index=False)
        
        # Generate summary
        summary = {
            "total_rows": len(cleaned_df),
            "columns_mapped": column_map,
            "validation": validation_results,
            "sample_data": cleaned_df.head(3).to_dict('records')  # Just 3 rows for context
        }
        
        return {
            "status": "success",
            "output_file": str(output_file),
            "summary": summary
        }
        
    except Exception as e:
        return {
            "status": "failed",
            "error": str(e)
        }