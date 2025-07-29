"""
Variant Builder Tool for creating Odoo product variants using template value IDs.
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
def variant_builder_tool(
    clear_products_file: str,
    llm_parsed_results_file: str,
    odoo_product_template_file: str,
    output_dir: str
) -> dict:
    """
    Generate product variant import CSV using template value IDs from Odoo template export.
    
    Args:
        clear_products_file: Path to clear products JSON file
        llm_parsed_results_file: Path to LLM parsed results JSON file  
        odoo_product_template_file: Path to exported Odoo product templates CSV
        output_dir: Directory to save variant import CSV
        
    Returns:
        Dict with variant generation statistics and results
    """
    
    # Create output directory
    output_path = Path(output_dir) / "variants"
    output_path.mkdir(parents=True, exist_ok=True)
    
    # Load original product data (includes SKU and price)
    with open(clear_products_file, 'r') as f:
        clear_products = json.load(f)
    
    with open(llm_parsed_results_file, 'r') as f:
        llm_products = json.load(f)
    
    # Combine all products with their attributes
    all_products = _combine_product_data(clear_products, llm_products)
    
    # Parse Odoo templates to understand template value IDs
    template_data = _parse_template_export(odoo_product_template_file)
    
    # Generate variants by matching products to templates and their value combinations
    variant_imports = []
    generation_stats = {
        "total_products": len(all_products),
        "variants_generated": 0,
        "template_matches": 0,
        "template_misses": 0,
        "attribute_misses": 0,
        "templates_processed": len(template_data)
    }
    
    variant_counter = 1
    
    for product in all_products:
        # Find matching template based on product name
        matching_template = _find_matching_template(product, template_data)
        
        if not matching_template:
            generation_stats["template_misses"] += 1
            print(f"No template match for product: {product.get('product_name', product.get('name', 'Unknown'))}")
            continue
        
        generation_stats["template_matches"] += 1
        
        # Find matching attribute value combination within the template
        template_value_ids = _find_template_value_combination(
            product, matching_template
        )
        
        if not template_value_ids:
            generation_stats["attribute_misses"] += 1
            print(f"No attribute combination match for product: {product.get('product_name', product.get('name', 'Unknown'))}")
            print(f"  Product attributes: {product.get('attributes', {})}")
            continue
        
        # Generate variant import record
        template_name = matching_template['template_name']
        sku = product.get('sku', '')
        price = float(product.get('price', 0.0))
        
        variant_import = {
            'name': template_name,
            'product_template_variant_value_ids/id': ','.join(template_value_ids),
            'default_code': sku,
            'standard_price': str(price)
        }
        
        variant_imports.append(variant_import)
        generation_stats["variants_generated"] += 1
        variant_counter += 1
    
    # Save variant import CSV
    output_file = output_path / "product_variant_import.csv"
    
    if variant_imports:
        fieldnames = ['name', 'product_template_variant_value_ids/id', 'default_code', 'standard_price']
        with open(output_file, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(variant_imports)
    
    # Generate statistics report
    stats_file = output_path / "variant_generation_stats.json"
    with open(stats_file, 'w') as f:
        json.dump(generation_stats, f, indent=2)
    
    # Save template analysis for debugging
    template_analysis_file = output_path / "template_analysis.json"
    with open(template_analysis_file, 'w') as f:
        json.dump(template_data, f, indent=2)
    
    # Generate missing SKUs report
    missing_skus = []
    generated_skus = set(variant['default_code'] for variant in variant_imports)
    
    # Load template SKUs to exclude them from missing report
    template_skus = set()
    try:
        templates_df = pd.read_csv(output_path.parent / "templates" / "new_templates.csv")
        template_skus = set(templates_df['default_code'].dropna().tolist())
        print(f"Loaded {len(template_skus)} SKUs from templates to exclude from missing report")
    except Exception as e:
        print(f"Warning: Could not load template SKUs: {e}")
    
    for product in all_products:
        sku = product.get('sku', '')
        product_name = product.get('product_name', '') or product.get('name', '')
        
        # Check if this product was not converted to a variant AND is not in templates
        if sku and sku not in generated_skus and sku not in template_skus:
            missing_skus.append({
                'sku': sku,
                'product_name': product_name,
                'source': product.get('source', 'unknown'),
                'reason': 'no_template_match' if not _find_matching_template(product, template_data) else 'no_attribute_match'
            })
    
    # Save missing SKUs report
    missing_skus_file = output_path / "missing_skus.json"
    with open(missing_skus_file, 'w') as f:
        json.dump(missing_skus, f, indent=2)
    
    # Also save as CSV for easy viewing
    missing_skus_csv = output_path / "missing_skus.csv"
    if missing_skus:
        with open(missing_skus_csv, 'w', newline='', encoding='utf-8') as csvfile:
            fieldnames = ['sku', 'product_name', 'source', 'reason']
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(missing_skus)
    
    return {
        "status": "success",
        "total_products_processed": len(all_products),
        "variants_generated": generation_stats["variants_generated"],
        "generation_rate": f"{(generation_stats['variants_generated'] / len(all_products)) * 100:.1f}%",
        "output_file": str(output_file),
        "stats_file": str(stats_file),
        "template_analysis_file": str(template_analysis_file),
        "missing_skus_file": str(missing_skus_file),
        "missing_skus_csv": str(missing_skus_csv),
        "missing_skus_count": len(missing_skus),
        "generation_stats": generation_stats
    }


def _parse_template_export(odoo_template_file: str) -> Dict[str, Dict]:
    """Parse Odoo template export to understand template value IDs by template."""
    
    template_data = {}
    df = pd.read_csv(odoo_template_file)
    
    current_template_id = None
    current_template_name = None
    
    for _, row in df.iterrows():
        template_id = row['id']
        template_name = row['name']
        attribute_value_desc = row['attribute_line_ids/product_template_value_ids/product_attribute_value_id']
        value_id = row['attribute_line_ids/product_template_value_ids/id']
        
        # Check if this is a new template definition
        if pd.notna(template_id) and template_id != '':
            current_template_id = template_id
            current_template_name = template_name
            
            # Initialize template if not exists
            if current_template_id not in template_data:
                template_data[current_template_id] = {
                    'template_id': current_template_id,
                    'template_name': current_template_name,
                    'attribute_values': {}
                }
        
        # Process attribute values (works for both template definition and continuation rows)
        if current_template_id and pd.notna(attribute_value_desc) and ':' in attribute_value_desc and pd.notna(value_id):
            attr_name, attr_value = attribute_value_desc.split(':', 1)
            attr_name = attr_name.strip().lower()
            attr_value = attr_value.strip()
            
            # Store the mapping: attribute_name -> {value -> template_value_id}
            if attr_name not in template_data[current_template_id]['attribute_values']:
                template_data[current_template_id]['attribute_values'][attr_name] = {}
            
            template_data[current_template_id]['attribute_values'][attr_name][attr_value] = value_id
    
    return template_data


def _combine_product_data(clear_products: List[Dict], llm_products: List[Dict]) -> List[Dict]:
    """Combine clear and LLM parsed products into unified dataset, with LLM results taking priority."""
    
    combined_products = []
    
    # Create index map for LLM products for quick lookup
    llm_by_index = {}
    for product in llm_products:
        index = product.get('index')
        if index is not None:
            llm_by_index[index] = product
    
    # Process clear products (regex parsed), but use LLM result if available
    for i, product in enumerate(clear_products):
        index = product.get('index', i)
        
        # Check if we have an LLM result for this index
        if index in llm_by_index:
            # Use LLM result instead
            llm_product = llm_by_index[index]
            
            # Convert all attribute values to strings for consistency
            attributes = {}
            
            # Add direct attributes from product level
            for attr_name in ['flavor', 'nicotine_mg', 'volume_ml', 'color', 'resistance_ohm', 'coil_type']:
                if attr_name in llm_product and llm_product[attr_name] is not None:
                    attributes[attr_name] = str(llm_product[attr_name])
            
            # Also check nested attributes (from LLM parsing)
            if 'attributes' in llm_product and isinstance(llm_product['attributes'], dict):
                for key, value in llm_product['attributes'].items():
                    if key not in ['index', 'brand', 'product_name', 'name', 'sku', 'price'] and value is not None:
                        attributes[key] = str(value)
            
            combined_product = {
                'index': index,
                'name': llm_product.get('name', ''),
                'sku': llm_product.get('sku', ''),
                'price': float(llm_product.get('price', 0)),
                'product_name': llm_product.get('product_name', ''),
                'brand': llm_product.get('brand', ''),
                'source': 'llm',
                'attributes': attributes
            }
        else:
            # Use regex result
            combined_product = {
                'index': index,
                'name': product.get('name', ''),
                'sku': product.get('sku', ''),
                'price': float(product.get('price', 0)),
                'product_name': product.get('product_name', ''),
                'brand': product.get('brand', ''),
                'source': 'regex'
            }
            
            # Add regex attributes from various possible fields
            attributes = {}
            if 'flavor' in product:
                attributes['flavor'] = str(product['flavor']) if product['flavor'] is not None else ''
            if 'nicotine_mg' in product:
                attributes['nicotine_mg'] = str(product['nicotine_mg']) if product['nicotine_mg'] is not None else ''
            if 'volume_ml' in product:
                attributes['volume_ml'] = str(product['volume_ml']) if product['volume_ml'] is not None else ''
            
            # Also check for regex_result field
            regex_result = product.get('regex_result', {})
            if regex_result:
                for key, value in regex_result.items():
                    if key not in ['product_name', 'confidence'] and value is not None:
                        attributes[key] = str(value)
            
            combined_product['attributes'] = attributes
        
        combined_products.append(combined_product)
    
    # Add any LLM products that don't have corresponding regex products
    for product in llm_products:
        index = product.get('index')
        # Check if this index was already processed in the clear_products loop
        if index is not None and not any(p['index'] == index for p in combined_products):
            # Convert all attribute values to strings for consistency
            attributes = {}
            
            # Add direct attributes from product level
            for attr_name in ['flavor', 'nicotine_mg', 'volume_ml', 'color', 'resistance_ohm', 'coil_type']:
                if attr_name in product and product[attr_name] is not None:
                    attributes[attr_name] = str(product[attr_name])
            
            # Also check nested attributes (from LLM parsing)
            if 'attributes' in product and isinstance(product['attributes'], dict):
                for key, value in product['attributes'].items():
                    if key not in ['index', 'brand', 'product_name', 'name', 'sku', 'price'] and value is not None:
                        attributes[key] = str(value)
            
            combined_product = {
                'index': index,
                'name': product.get('name', ''),
                'sku': product.get('sku', ''),
                'price': float(product.get('price', 0)),
                'product_name': product.get('product_name', ''),
                'brand': product.get('brand', ''),
                'source': 'llm',
                'attributes': attributes
            }
            
            combined_products.append(combined_product)
    
    return combined_products


def _find_matching_template(product: Dict, template_data: Dict[str, Dict]) -> Optional[Dict]:
    """Find the template that matches the product name."""
    
    product_name = product.get('product_name', '') or ''
    if hasattr(product_name, 'strip'):
        product_name = product_name.strip()
    else:
        product_name = str(product_name) if product_name is not None else ''
    
    if not product_name:
        product_name = product.get('name', '') or ''
        if hasattr(product_name, 'strip'):
            product_name = product_name.strip()
        else:
            product_name = str(product_name) if product_name is not None else ''
    
    if not product_name:
        return None
    
    # Try exact match first
    for template_id, template_info in template_data.items():
        template_name = template_info.get('template_name', '') or ''
        if hasattr(template_name, 'strip'):
            template_name = template_name.strip()
        else:
            template_name = str(template_name) if template_name is not None else ''
        
        if product_name == template_name:
            return template_info
    
    # Try fuzzy matching - check if product name is contained in template name or vice versa
    product_name_lower = product_name.lower()
    
    for template_id, template_info in template_data.items():
        template_name = template_info.get('template_name', '') or ''
        if hasattr(template_name, 'strip'):
            template_name = template_name.strip().lower()
        else:
            template_name = str(template_name).lower() if template_name is not None else ''
        
        # Check if they share significant overlap
        if product_name_lower in template_name or template_name in product_name_lower:
            return template_info
        
        # Check word-by-word similarity for compound names
        product_words = set(product_name_lower.split())
        template_words = set(template_name.split())
        
        # If at least 70% of words match, consider it a match
        if len(product_words) > 0 and len(template_words) > 0:
            overlap = len(product_words.intersection(template_words))
            similarity = overlap / min(len(product_words), len(template_words))
            if similarity >= 0.7:
                return template_info
    
    return None


def _find_template_value_combination(product: Dict, template: Dict) -> List[str]:
    """Find the template value IDs that match the product's attributes."""
    
    product_attributes = product.get('attributes', {})
    template_values = template.get('attribute_values', {})
    
    matched_value_ids = []
    
    # For each attribute type in the template, try to find a matching value
    for attr_name, value_mapping in template_values.items():
        
        # Normalize attribute name for comparison
        attr_name_normalized = attr_name.lower().strip()
        
        # Find matching attribute in product
        product_value = None
        
        # Direct match
        if attr_name_normalized in product_attributes:
            product_value = product_attributes[attr_name_normalized]
        
        # Try common variations
        elif attr_name_normalized == 'flavor' and 'flavor' in product_attributes:
            product_value = product_attributes['flavor']
        elif 'nicotine' in attr_name_normalized and 'nicotine_mg' in product_attributes:
            product_value = product_attributes['nicotine_mg']
        elif attr_name_normalized == 'nicotine level' and 'nicotine_mg' in product_attributes:
            product_value = product_attributes['nicotine_mg']
        elif 'size' in attr_name_normalized and 'volume_ml' in product_attributes:
            product_value = product_attributes['volume_ml']
        elif attr_name_normalized == 'color' and 'color' in product_attributes:
            product_value = product_attributes['color']
        elif 'resistance' in attr_name_normalized and 'resistance_ohm' in product_attributes:
            product_value = product_attributes['resistance_ohm']
        
        if product_value is not None:
            product_value_str = str(product_value)
            if hasattr(product_value_str, 'strip'):
                product_value_str = product_value_str.strip()
            else:
                product_value_str = str(product_value_str) if product_value_str is not None else ''
            
            # Try to find exact match in template values
            if product_value_str in value_mapping:
                matched_value_ids.append(value_mapping[product_value_str])
            else:
                # Try fuzzy matching for the value
                best_match = _find_best_value_match(product_value_str, value_mapping)
                if best_match:
                    matched_value_ids.append(value_mapping[best_match])
    
    return matched_value_ids


def _find_best_value_match(product_value: str, template_value_mapping: Dict[str, str]) -> Optional[str]:
    """Find the best matching template value for a product value."""
    
    if product_value is None:
        return None
    
    product_value_str = str(product_value)
    if hasattr(product_value_str, 'strip'):
        product_value_lower = product_value_str.lower().strip()
    else:
        product_value_lower = str(product_value_str).lower() if product_value_str is not None else ''
    
    if not product_value_lower:
        return None
    
    # Try exact match first
    for template_value in template_value_mapping.keys():
        if template_value is None:
            continue
        template_value_str = str(template_value)
        if hasattr(template_value_str, 'strip'):
            template_lower = template_value_str.lower().strip()
        else:
            template_lower = str(template_value_str).lower() if template_value_str is not None else ''
        
        if template_lower == product_value_lower:
            return template_value
    
    # For numeric values, try to match numbers
    if product_value_lower.replace('.', '').replace('-', '').isdigit():
        product_number = re.findall(r'\d+(?:\.\d+)?', product_value_lower)
        if product_number:
            product_num = product_number[0]
            for template_value in template_value_mapping.keys():
                if template_value is None:
                    continue
                template_value_str = str(template_value)
                template_numbers = re.findall(r'\d+(?:\.\d+)?', template_value_str.lower())
                if template_numbers and template_numbers[0] == product_num:
                    return template_value
    
    # Try partial matching for strings
    for template_value in template_value_mapping.keys():
        if template_value is None:
            continue
        template_value_str = str(template_value)
        if hasattr(template_value_str, 'strip'):
            template_lower = template_value_str.lower().strip()
        else:
            template_lower = str(template_value_str).lower() if template_value_str is not None else ''
        
        # Check if product value is contained in template value
        if product_value_lower in template_lower:
            return template_value
        
        # Check if template value is contained in product value
        if template_lower in product_value_lower:
            return template_value
        
        # Check word-by-word similarity
        product_words = set(product_value_lower.split())
        template_words = set(template_lower.split())
        
        if len(product_words) > 0 and len(template_words) > 0:
            overlap = len(product_words.intersection(template_words))
            similarity = overlap / min(len(product_words), len(template_words))
            if similarity >= 0.8:  # High similarity threshold
                return template_value
    
    return None


