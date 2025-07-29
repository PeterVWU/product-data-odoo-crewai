"""
Attribute Builder Tool for generating Odoo product attributes CSV.
"""

import json
import pandas as pd
import csv
from pathlib import Path
from typing import Dict, List, Set, Any
from crewai.tools import tool


@tool
def attribute_builder_tool(
    clear_products_file: str,
    llm_parsed_results_file: str,
    odoo_attributes_file: str,
    output_dir: str
) -> dict:
    """
    Generate Odoo product attributes CSV from parsed product data, reusing existing Odoo attributes.
    
    Args:
        clear_products_file: Path to clear products JSON file
        llm_parsed_results_file: Path to LLM parsed results JSON file
        odoo_attributes_file: Path to existing Odoo attributes CSV file
        output_dir: Directory to save attributes CSV
        
    Returns:
        Dict with attribute generation statistics and results
    """
    
    # Load existing Odoo attributes
    existing_attributes = _load_existing_attributes(odoo_attributes_file)
    
    # Load product data
    with open(clear_products_file, 'r') as f:
        clear_products = json.load(f)
    
    with open(llm_parsed_results_file, 'r') as f:
        llm_products = json.load(f)
    
    # Collect all unique attributes and their values
    attribute_data = {}
    
    # Process clear products (regex parsed)
    for product in clear_products:
        _collect_product_attributes(product, attribute_data, source='regex')
    
    # Process LLM parsed products
    for product in llm_products:
        _collect_product_attributes(product, attribute_data, source='llm')
    
    # Generate two separate CSVs: existing attributes and new attributes
    existing_attr_csv_data = []
    new_attr_csv_data = []
    attribute_summary = {}
    reuse_stats = {'existing_attributes': 0, 'new_attributes': 0, 'existing_values': 0, 'new_values': 0}
    
    for attr_name, attr_info in attribute_data.items():
        # Check if attribute already exists in Odoo (use raw name first, then formatted)
        existing_attr_info = _find_existing_attribute(attr_name, existing_attributes)
        formatted_attr_name = None  # Initialize to avoid reference errors
        
        # If not found with raw name, try formatted name
        if not existing_attr_info:
            formatted_attr_name = _format_attribute_name(attr_name)
            existing_attr_info = _find_existing_attribute(formatted_attr_name, existing_attributes)
        
        if existing_attr_info:
            # Reuse existing attribute
            attr_external_id = existing_attr_info['id']
            attr_display_type = existing_attr_info.get('display_type', 'radio')
            # Use the existing attribute name from Odoo, or formatted name if we had to format it
            attr_display_name = existing_attr_info['name']
            reuse_stats['existing_attributes'] += 1
            
            # Process values for existing attribute (only add new ones)
            unique_values = sorted(attr_info['values'])
            existing_values = existing_attr_info.get('values', {})
            new_values_for_attr = []
            
            for value in unique_values:
                if value is not None and str(value).strip():
                    value_str = str(value).strip()
                    
                    # Check if value already exists
                    existing_value_id = _find_existing_value(value_str, existing_values)
                    
                    if existing_value_id:
                        reuse_stats['existing_values'] += 1
                    else:
                        new_values_for_attr.append(value_str)
                        reuse_stats['new_values'] += 1
            
            # Add new values to existing attributes CSV
            if new_values_for_attr:
                for i, value_str in enumerate(new_values_for_attr):
                    if i == 0:
                        # First value - include attribute info (id,name,value/value format)
                        existing_attr_csv_data.append({
                            'id': attr_external_id,
                            'name': attr_display_name,
                            'value/value': value_str
                        })
                    else:
                        # Additional values - empty id and name
                        existing_attr_csv_data.append({
                            'id': '',
                            'name': '',
                            'value/value': value_str
                        })
            
        else:
            # Create new attribute
            attr_external_id = f"attr_{_sanitize_name(attr_name)}"
            attr_display_type = _determine_display_type(attr_name, attr_info['values'])
            reuse_stats['new_attributes'] += 1
            
            # Process values for new attribute
            unique_values = sorted(attr_info['values'])
            new_values_for_attr = []
            
            for value in unique_values:
                if value is not None and str(value).strip():
                    value_str = str(value).strip()
                    new_values_for_attr.append(value_str)
                    reuse_stats['new_values'] += 1
            
            # Add new attribute to new attributes CSV
            if new_values_for_attr:
                for i, value_str in enumerate(new_values_for_attr):
                    if i == 0:
                        # First value - include attribute info (value/value,attribute,display_type,create_variant format)
                        new_attr_csv_data.append({
                            'value/value': value_str,
                            'attribute': formatted_attr_name,
                            'display_type': attr_display_type,
                            'create_variant': 'instantly'
                        })
                    else:
                        # Additional values - just the value
                        new_attr_csv_data.append({
                            'value/value': value_str,
                            'attribute': '',
                            'display_type': '',
                            'create_variant': ''
                        })
        
        # Store summary stats
        attribute_summary[attr_name] = {
            'external_id': attr_external_id,
            'display_type': attr_display_type,
            'value_count': len(attr_info['values']),
            'total_usage': attr_info['count'],
            'sources': list(attr_info['sources']),
            'status': 'existing' if existing_attr_info else 'new'
        }
    
    # Save both CSV files
    output_path = Path(output_dir) / "attributes"
    output_path.mkdir(parents=True, exist_ok=True)
    
    # Save existing attributes CSV (for adding values to existing attributes)
    existing_attrs_file = output_path / "existing_attributes_values.csv"
    if existing_attr_csv_data:
        with open(existing_attrs_file, 'w', newline='', encoding='utf-8') as f:
            fieldnames = ['id', 'name', 'value/value']
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(existing_attr_csv_data)
    
    # Save new attributes CSV (for creating new attributes)
    new_attrs_file = output_path / "new_attributes.csv"
    if new_attr_csv_data:
        with open(new_attrs_file, 'w', newline='', encoding='utf-8') as f:
            fieldnames = ['value/value', 'attribute', 'display_type', 'create_variant']
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(new_attr_csv_data)
    
    # Also keep the original combined CSV for backward compatibility
    attributes_file = output_path / "attributes.csv"
    all_csv_data = []
    
    # Convert existing attributes to original format
    for row in existing_attr_csv_data:
        if row['id']:  # First row of attribute
            all_csv_data.append({
                'value': row['value/value'],
                'attribute': '',
                'attribute/id': row['id'],
                'display_type': '',
                'create_variant': ''
            })
        else:  # Additional values
            all_csv_data.append({
                'value': row['value/value'],
                'attribute': '',
                'attribute/id': '',
                'display_type': '',
                'create_variant': ''
            })
    
    # Add new attributes (convert from new format to old format)
    for row in new_attr_csv_data:
        if row['attribute']:  # First row of attribute
            all_csv_data.append({
                'value': row['value/value'],
                'attribute': row['attribute'],
                'attribute/id': '',
                'display_type': row['display_type'],
                'create_variant': row['create_variant']
            })
        else:  # Additional values
            all_csv_data.append({
                'value': row['value/value'],
                'attribute': '',
                'attribute/id': '',
                'display_type': '',
                'create_variant': ''
            })
    
    # Write combined CSV
    with open(attributes_file, 'w', newline='', encoding='utf-8') as f:
        fieldnames = ['value', 'attribute', 'attribute/id', 'display_type', 'create_variant']
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(all_csv_data)
    
    # Save attribute summary
    summary_file = output_path / "attribute_summary.json"
    with open(summary_file, 'w') as f:
        json.dump(attribute_summary, f, indent=2)
    
    return {
        'status': 'success',
        'total_attributes': len(attribute_data),
        'total_records': len(all_csv_data),
        'existing_attributes_records': len(existing_attr_csv_data),
        'new_attributes_records': len(new_attr_csv_data),
        'clear_products_processed': len(clear_products),
        'llm_products_processed': len(llm_products),
        'reuse_statistics': reuse_stats,
        'attribute_summary': attribute_summary,
        'output_files': {
            'existing_attributes_csv': str(existing_attrs_file) if existing_attr_csv_data else None,
            'new_attributes_csv': str(new_attrs_file) if new_attr_csv_data else None,
            'combined_attributes_csv': str(attributes_file),
            'summary': str(summary_file)
        }
    }


def _collect_product_attributes(product: Dict[str, Any], attribute_data: Dict, source: str):
    """Collect all attributes from a product into the global attribute data."""
    
    # Standard attribute fields
    standard_attrs = ['flavor', 'nicotine_mg', 'volume_ml', 'brand', 'color', 'resistance', 'model']
    
    for attr_name in standard_attrs:
        if attr_name in product and product[attr_name] is not None:
            value = product[attr_name]
            _add_attribute_value(attribute_data, attr_name, value, source)
    
    # Check for nested attributes (from LLM parsing)
    if 'attributes' in product and isinstance(product['attributes'], dict):
        for attr_name, value in product['attributes'].items():
            if value is not None:
                _add_attribute_value(attribute_data, attr_name, value, source)
    
    # Handle additional dynamic attributes (any other fields)
    excluded_fields = {'product_name', 'name', 'index', 'confidence', 'attributes', 'original_name', 'sku', 'price'}
    for attr_name, value in product.items():
        if attr_name not in excluded_fields and attr_name not in standard_attrs and value is not None:
            _add_attribute_value(attribute_data, attr_name, value, source)


def _add_attribute_value(attribute_data: Dict, attr_name: str, value: Any, source: str):
    """Add an attribute value to the global collection."""
    if attr_name not in attribute_data:
        attribute_data[attr_name] = {
            'values': set(),
            'count': 0,
            'sources': set()
        }
    
    # Handle different value types
    if isinstance(value, list):
        # If it's a list, process each item separately
        for item in value:
            if item is not None:
                _add_attribute_value(attribute_data, attr_name, item, source)
        return
    elif isinstance(value, dict):
        # If it's a dict, skip it (can't be used as attribute value)
        return
    elif isinstance(value, str):
        value = value.strip()
        if not value:  # Skip empty strings
            return
    elif value is None:
        return
    
    # Convert to string for consistent handling
    value_str = str(value)
    
    attribute_data[attr_name]['values'].add(value_str)
    attribute_data[attr_name]['count'] += 1
    attribute_data[attr_name]['sources'].add(source)


def _sanitize_name(name: str) -> str:
    """Sanitize a name for use in external IDs."""
    import re
    # Convert to lowercase, replace spaces and special chars with underscores
    sanitized = re.sub(r'[^a-zA-Z0-9_]', '_', str(name).lower())
    # Remove multiple consecutive underscores
    sanitized = re.sub(r'_+', '_', sanitized)
    # Remove leading/trailing underscores
    sanitized = sanitized.strip('_')
    return sanitized or 'unknown'


def _format_attribute_name(attr_name: str) -> str:
    """Format attribute name for display in Odoo."""
    # Convert snake_case to Title Case
    words = attr_name.replace('_', ' ').split()
    formatted_words = []
    
    for word in words:
        # Handle special cases
        if word.lower() == 'mg':
            formatted_words.append('(mg)')
        elif word.lower() == 'ml':
            formatted_words.append('(mL)')
        elif word.lower() == 'ohm':
            formatted_words.append('(Ω)')
        else:
            formatted_words.append(word.capitalize())
    
    return ' '.join(formatted_words)


def _load_existing_attributes(odoo_attributes_file: str) -> Dict[str, Dict]:
    """Load existing Odoo attributes from CSV file."""
    existing_attributes = {}
    
    try:
        df = pd.read_csv(odoo_attributes_file)
        
        current_attr = None
        for _, row in df.iterrows():
            attr_id = row['id'] if pd.notna(row['id']) and row['id'].strip() else None
            attr_name = row['name'] if pd.notna(row['name']) and row['name'].strip() else None
            value_id = row['value_ids/id'] if pd.notna(row['value_ids/id']) else None
            value_name = row['value_ids/name'] if pd.notna(row['value_ids/name']) else None
            
            if attr_id and attr_name:
                # New attribute definition
                current_attr = attr_name
                if current_attr not in existing_attributes:
                    existing_attributes[current_attr] = {
                        'id': attr_id,
                        'name': attr_name,
                        'values': {}
                    }
            
            # Add value to current attribute
            if current_attr and value_id and value_name:
                existing_attributes[current_attr]['values'][value_name] = value_id
                
    except Exception as e:
        print(f"Warning: Could not load existing attributes: {e}")
        
    return existing_attributes


def _find_existing_attribute(attr_name: str, existing_attributes: Dict) -> Dict:
    """Find existing attribute by name (case-insensitive)."""
    attr_name_lower = attr_name.lower()
    
    for existing_name, attr_info in existing_attributes.items():
        if existing_name.lower() == attr_name_lower:
            return attr_info
    
    # Check for common variations - map product attributes to exact Odoo attribute names
    attr_variations = {
        'nicotine level': ['nicotine', 'nicotine_mg', 'nicotine strength', 'nicotine_mg_range', 'nicotine_mg_min', 'nicotine_mg_max'],
        'flavor': ['flavor'],
        'brand': ['brand'],
        'color': ['color'],
        'resistance': ['resistance', 'resistance_ohm', 'ohm'],
        'size': ['volume', 'volume_ml', 'capacity'],
        'coil type': ['coil_type', 'coil model', 'coil_model']
    }
    
    for existing_name, attr_info in existing_attributes.items():
        existing_lower = existing_name.lower()
        for standard_name, variations in attr_variations.items():
            if existing_lower == standard_name and attr_name_lower in variations:
                return attr_info
            elif attr_name_lower == standard_name and existing_lower in variations:
                return attr_info
    
    return None


def _find_existing_value(value_name: str, existing_values: Dict) -> str:
    """Find existing value by name (case-insensitive)."""
    value_name_lower = value_name.lower().strip()
    
    for existing_value_name, value_id in existing_values.items():
        if existing_value_name.lower().strip() == value_name_lower:
            return value_id
    
    return None


def _determine_display_type(attr_name: str, values: Set) -> str:
    """Determine the appropriate Odoo display type for an attribute."""
    
    # Check if all values are numeric
    numeric_values = []
    for value in values:
        try:
            if isinstance(value, (int, float)):
                numeric_values.append(value)
            elif isinstance(value, str) and value.replace('.', '').replace('-', '').isdigit():
                numeric_values.append(float(value))
        except:
            pass
    
    # If most values are numeric, use radio (for discrete numeric values)
    if len(numeric_values) >= len(values) * 0.8:
        return 'radio'
    
    # For non-numeric attributes with many values, use select
    if len(values) > 10:
        return 'select'
    
    # For attributes with few values, use radio
    return 'radio'