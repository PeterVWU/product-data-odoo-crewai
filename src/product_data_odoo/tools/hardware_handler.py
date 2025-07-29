"""
Hardware Products Handler Tool for processing remaining products with single variant_type attribute.
"""

import json
import pandas as pd
import csv
import re
from pathlib import Path
from typing import Dict, List, Set, Any, Optional
from collections import defaultdict
from crewai.tools import tool


@tool
def hardware_products_handler(
    missing_skus_file: str,
    llm_parsed_results_file: str,
    output_dir: str
) -> dict:
    """
    Handle remaining hardware products by creating templates with single variant_type attribute.
    
    Args:
        missing_skus_file: Path to missing SKUs JSON file
        llm_parsed_results_file: Path to LLM parsed results JSON file
        output_dir: Directory to save hardware import CSVs
        
    Returns:
        Dict with hardware processing statistics and results
    """
    
    # Create output directory
    output_path = Path(output_dir) / "hardware"
    output_path.mkdir(parents=True, exist_ok=True)
    
    # Load missing SKUs
    with open(missing_skus_file, 'r') as f:
        missing_skus = json.load(f)
    
    # Load LLM parsed results to get attribute data
    with open(llm_parsed_results_file, 'r') as f:
        llm_products = json.load(f)
    
    # Create SKU to product mapping
    sku_to_product = {}
    for product in llm_products:
        sku = product.get('sku', '')
        if sku:
            sku_to_product[sku] = product
    
    # Group missing SKUs by product_name
    product_groups = defaultdict(list)
    for missing_sku in missing_skus:
        product_name = missing_sku['product_name']
        sku = missing_sku['sku']
        
        # Find the full product data
        product_data = sku_to_product.get(sku, {})
        product_groups[product_name].append({
            'sku': sku,
            'product_name': product_name,
            'product_data': product_data
        })
    
    # Generate hardware attributes, templates, and variants
    hardware_attributes = []
    hardware_templates = []
    hardware_variants = []
    
    stats = {
        "product_groups": len(product_groups),
        "total_missing_skus": len(missing_skus),
        "attributes_created": 0,
        "templates_created": 0,
        "variants_created": 0
    }
    
    # Create single shared attribute for all hardware products
    shared_attribute_id = "variant_type"
    hardware_attributes.append({
        'id': shared_attribute_id,  
        'name': 'Variant Type',
        'display_type': 'radio',
        'create_variant': 'always'
    })
    
    # Track unique attribute values to avoid duplicates
    unique_attribute_values = set()
    
    # Process each product group
    for product_name, products in product_groups.items():
        
        # Create variant type values for this product group
        variant_values = []
        variant_value_ids = []
        
        for product in products:
            product_data = product['product_data']
            
            # Combine all attributes into a single variant description
            variant_parts = []
            
            # Check for various attribute types and combine them
            for attr_name in ['model', 'resistance', 'color', 'resistance_ohm', 'coil_type', 'volume_ml']:
                if attr_name in product_data and product_data[attr_name]:
                    variant_parts.append(str(product_data[attr_name]))
            
            # Also check nested attributes
            if 'attributes' in product_data and isinstance(product_data['attributes'], dict):
                for key, value in product_data['attributes'].items():
                    if value and key not in ['index', 'brand', 'product_name', 'name', 'sku', 'price']:
                        variant_parts.append(str(value))
            
            # If no attributes found, use SKU as variant identifier
            if not variant_parts:
                # Extract meaningful part from SKU or use last part of product name
                sku_suffix = product['sku'].split('ONT')[-1] if 'ONT' in product['sku'] else product['sku']
                variant_parts.append(f"Variant {sku_suffix}")
            
            # Create variant value description
            variant_description = " ".join(variant_parts)
            
            # Clean up the description
            variant_description = re.sub(r'\s+', ' ', variant_description).strip()
            
            # Create External ID for this variant value (make it unique across all hardware)
            safe_description = re.sub(r'[^a-zA-Z0-9]', '_', variant_description.lower())
            safe_product = re.sub(r'[^a-zA-Z0-9]', '_', product_name.lower())
            variant_value_id = f"variant_{safe_product}_{safe_description}"[:100]  # Limit length
            
            variant_values.append({
                'description': variant_description,
                'value_id': variant_value_id,
                'product': product
            })
            variant_value_ids.append(variant_value_id)
        
        # Skip if no variants found
        if not variant_values:
            continue
        
        # Add attribute values to the shared attribute (avoid duplicates)
        for variant_value in variant_values:
            value_description = variant_value['description']
            # Only add if we haven't seen this value description before
            if value_description not in unique_attribute_values:
                unique_attribute_values.add(value_description)
                hardware_attributes.append({
                    'id': variant_value['value_id'],
                    'name': value_description,
                    'attribute_id/id': shared_attribute_id,
                    'display_type': '',
                    'create_variant': ''
                })
        
        # Create template using shared attribute
        if len(variant_values) > 1:
            # Create template External ID
            safe_product_name = re.sub(r'[^a-zA-Z0-9]', '_', product_name.lower())
            template_id = f"template_{safe_product_name}"[:100]
            
            # Calculate average price for template
            prices = [float(v['product']['product_data'].get('price', 0)) for v in variant_values]
            avg_price = sum(prices) / len(prices) if prices else 0
            
            # Add template
            hardware_templates.append({
                'id': template_id,
                'name': product_name,
                'categ_id/id': '__export__.product_category_9_bc43a31e',  # Coil category
                'type': 'consu',
                'sale_ok': 'True',
                'standard_price': f"{avg_price:.2f}",
                'default_code': '',  # No SKU for template
                'attribute_line_ids/attribute_id/id': shared_attribute_id,
                'attribute_line_ids/value_ids/id': ','.join(variant_value_ids)
            })
            
            # Add variants
            for variant_value in variant_values:
                product_info = variant_value['product']
                product_data = product_info['product_data']
                
                hardware_variants.append({
                    'name': product_name,
                    'product_template_variant_value_ids/id': variant_value['value_id'],
                    'default_code': product_info['sku'],
                    'standard_price': str(float(product_data.get('price', 0)))
                })
            
            stats["templates_created"] += 1
            stats["variants_created"] += len(variant_values)
        
        else:
            # Single product - create as simple template (no variants)
            product_info = variant_values[0]['product']
            product_data = product_info['product_data']
            
            # Create simple template External ID
            safe_product_name = re.sub(r'[^a-zA-Z0-9]', '_', product_name.lower())
            template_id = f"simple_{safe_product_name}_{product_info['sku']}"[:100]
            
            # Add simple template
            hardware_templates.append({
                'id': template_id,
                'name': product_name,
                'categ_id/id': '__export__.product_category_9_bc43a31e',  # Coil category
                'type': 'consu',
                'sale_ok': 'True',
                'standard_price': str(float(product_data.get('price', 0))),
                'default_code': product_info['sku'],
                'attribute_line_ids/attribute_id/id': '',
                'attribute_line_ids/value_ids/id': ''
            })
            
            stats["templates_created"] += 1
    
    # Count unique attributes created (should be 1 now)
    stats["attributes_created"] = 1  # Only one shared attribute
    
    # Save hardware attributes CSV in correct format with proper quoting
    attributes_file = output_path / "hardware_attributes.csv"
    if hardware_attributes:
        with open(attributes_file, 'w', newline='', encoding='utf-8') as csvfile:
            # Write header with quotes
            csvfile.write('"id","name","value_ids/id","value_ids/name"\n')
            
            # Group attributes by their main attribute ID
            attributes_by_id = {}
            for attr in hardware_attributes:
                if attr.get('display_type') == 'radio':  # Main attribute
                    attributes_by_id[attr['id']] = {
                        'main_attr': attr,
                        'values': []
                    }
            
            # Add values to their respective attributes
            for attr in hardware_attributes:
                if attr.get('attribute_id/id'):  # This is a value
                    parent_id = attr['attribute_id/id']
                    if parent_id in attributes_by_id:
                        attributes_by_id[parent_id]['values'].append(attr)
            
            # Write in correct format: main attribute first, then its values
            for attr_id, attr_data in attributes_by_id.items():
                main_attr = attr_data['main_attr']
                values = attr_data['values']
                
                if values:  # Only write if there are values
                    # First row: main attribute with first value (no quotes around main attribute ID)
                    first_value = values[0]
                    csvfile.write(f'{main_attr["id"]},"{main_attr["name"]}",{first_value["id"]},"{first_value["name"]}"\n')
                    
                    # Subsequent rows: empty id/name with quotes, values with quotes around names
                    for value in values[1:]:
                        csvfile.write(f'"","",{value["id"]},"{value["name"]}"\n')
    
    # Save hardware templates CSV
    templates_file = output_path / "hardware_templates.csv"
    if hardware_templates:
        fieldnames = ['id', 'name', 'categ_id/id', 'type', 'sale_ok', 'standard_price', 
                     'default_code', 'attribute_line_ids/attribute_id/id', 'attribute_line_ids/value_ids/id']
        with open(templates_file, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(hardware_templates)
    
    # Save hardware variants CSV
    variants_file = output_path / "hardware_variants.csv"
    if hardware_variants:
        fieldnames = ['name', 'product_template_variant_value_ids/id', 'default_code', 'standard_price']
        with open(variants_file, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(hardware_variants)
    
    # Save processing report
    report_file = output_path / "hardware_processing_report.json"
    processing_report = {
        "stats": stats,
        "product_groups": list(product_groups.keys()),
        "files_created": {
            "attributes": str(attributes_file),
            "templates": str(templates_file),
            "variants": str(variants_file)
        }
    }
    
    with open(report_file, 'w') as f:
        json.dump(processing_report, f, indent=2)
    
    return {
        "status": "success",
        "stats": stats,
        "attributes_file": str(attributes_file),
        "templates_file": str(templates_file), 
        "variants_file": str(variants_file),
        "report_file": str(report_file)
    }