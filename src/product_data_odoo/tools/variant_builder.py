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
    Generate product variant import CSV using existing variant IDs from Odoo exports.
    
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
    
    # Load existing Odoo variants for ID mapping
    existing_variants = _load_existing_variants(output_dir)
    
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
        
        # Find matching existing variant ID
        existing_variant_id = _find_existing_variant_id(
            product, matching_template, existing_variants
        )
        
        if not existing_variant_id:
            generation_stats["attribute_misses"] += 1
            print(f"No existing variant ID found for product: {product.get('product_name', product.get('name', 'Unknown'))}")
            print(f"  Product attributes: {product.get('attributes', {})}")
            continue
        
        # Find matching attribute value combination within the template
        template_value_ids = _find_template_value_combination(
            product, matching_template
        )
        
        if not template_value_ids:
            generation_stats["attribute_misses"] += 1
            print(f"No attribute combination match for product: {product.get('product_name', product.get('name', 'Unknown'))}")
            print(f"  Product attributes: {product.get('attributes', {})}")
            continue
        
        # Generate variant import record with existing variant ID
        template_name = matching_template['template_name']
        sku = product.get('sku', '')
        price = float(product.get('price', 0.0))
        
        variant_import = {
            'id': existing_variant_id,
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
        fieldnames = ['id', 'name', 'product_template_variant_value_ids/id', 'default_code', 'standard_price']
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


def _load_existing_variants(output_dir: str) -> Dict[str, Dict]:
    """
    Load existing Odoo variants from odoo_product_variant.csv.
    Handles multi-row variants where additional attributes are in subsequent rows with empty IDs.
    
    Returns:
        Dict mapping variant_key (template_name|combined_attributes) to variant info
    """
    
    # Construct path to odoo_product_variant.csv (in src directory)
    base_path = Path(output_dir).parent / "src" / "product_data_odoo" / "odoo_product_variant.csv"
    
    if not base_path.exists():
        print(f"Warning: Could not find odoo_product_variant.csv at {base_path}")
        return {}
    
    existing_variants = {}
    
    try:
        df = pd.read_csv(base_path)
        
        i = 0
        while i < len(df):
            row = df.iloc[i]
            variant_id = str(row['ID']) if pd.notna(row['ID']) else ""
            template_name = str(row['Name']) if pd.notna(row['Name']) else ""
            variant_values = str(row['Variant Values']) if pd.notna(row['Variant Values']) else ""
            
            # Skip rows with empty variant ID (these are continuation rows)
            if not variant_id.strip():
                i += 1
                continue
            
            # This is a main variant row - collect all its attributes
            all_attributes = []
            if variant_values.strip():
                all_attributes.append(variant_values.strip())
            
            # Look ahead for continuation rows (empty ID/Name but has Variant Values)
            j = i + 1
            while j < len(df):
                next_row = df.iloc[j]
                next_id = str(next_row['ID']) if pd.notna(next_row['ID']) else ""
                next_name = str(next_row['Name']) if pd.notna(next_row['Name']) else ""
                next_values = str(next_row['Variant Values']) if pd.notna(next_row['Variant Values']) else ""
                
                # If next row has empty ID/Name but has values, it's a continuation
                if not next_id.strip() and not next_name.strip() and next_values.strip():
                    all_attributes.append(next_values.strip())
                    j += 1
                else:
                    # Next row is a new variant or end of data
                    break
            
            # Combine all attributes for this variant
            combined_attributes = "|".join(sorted(all_attributes)) if all_attributes else ""
            
            # Parse attributes into a dictionary for easier matching
            attribute_dict = {}
            for attr in all_attributes:
                if ":" in attr:
                    attr_name, attr_value = attr.split(":", 1)
                    # Convert to our internal attribute format for consistent matching
                    original_attr_name = attr_name.strip()
                    attr_value = attr_value.strip()
                    
                    # Map Odoo attribute names to our internal format using the same logic as _convert_to_odoo_attribute_name
                    if original_attr_name.lower() == "flavor":
                        attribute_dict["flavor"] = attr_value
                    elif original_attr_name.lower() == "nicotine level":
                        attribute_dict["nicotine level"] = attr_value
                    elif original_attr_name.lower() == "color":
                        attribute_dict["color"] = attr_value
                    elif original_attr_name.lower() == "resistance":
                        attribute_dict["resistance"] = attr_value
                    elif "coil" in original_attr_name.lower() and ("type" in original_attr_name.lower() or "model" in original_attr_name.lower()):
                        if "type" in original_attr_name.lower():
                            attribute_dict["coil type"] = attr_value
                        else:
                            attribute_dict["coil type"] = attr_value  # Use same key for both type and model
                    else:
                        # Keep original format for other attributes
                        attribute_dict[original_attr_name.lower()] = attr_value
            
            # Create variant entry
            existing_variants[variant_id] = {
                'id': variant_id,
                'template_name': template_name,
                'all_attributes': all_attributes,
                'combined_attributes': combined_attributes,
                'attribute_dict': attribute_dict
            }
            
            # Also create lookup by template name + attributes combination
            variant_key = f"{template_name}|{combined_attributes}"
            if variant_key not in existing_variants:
                existing_variants[variant_key] = existing_variants[variant_id]
            
            print(f"Loaded variant {variant_id}: {template_name} with attributes: {all_attributes}")
            
            # Move to the next unprocessed row
            i = j
        
        print(f"Loaded {len([k for k in existing_variants.keys() if k.startswith('__export__')])} existing variants from Odoo")
        
    except Exception as e:
        print(f"Error loading existing variants: {e}")
    
    return existing_variants


def _find_existing_variant_id(product: Dict, template: Dict, existing_variants: Dict[str, Dict]) -> Optional[str]:
    """
    Find the existing variant ID that matches the product's template name and attributes.
    Now works with multi-attribute variants that have complete attribute dictionaries.
    
    Args:
        product: Product data with attributes
        template: Template data
        existing_variants: Dict of existing variants with complete attribute information
        
    Returns:
        Existing variant ID or None if not found
    """
    
    template_name = str(template.get('template_name', '')) if template.get('template_name') is not None else ''
    product_attributes = product.get('attributes', {})
    
    print(f"Looking for variant: {template_name} with attributes: {product_attributes}")
    
    # Try exact matching first - find variants with matching template name
    template_name_lower = template_name.lower()
    
    for variant_id, variant_info in existing_variants.items():
        # Skip non-ID keys (template+attribute combinations)
        if not variant_id.startswith('__export__.product_product_'):
            continue
            
        stored_template_name = variant_info.get('template_name', '')
        stored_template_lower = str(stored_template_name).lower() if stored_template_name else ""
        
        # Check if template names match
        if template_name_lower != stored_template_lower:
            continue
        
        # Template matches - now check if attributes match
        stored_attribute_dict = variant_info.get('attribute_dict', {})
        
        # NEW LOGIC: Use stored variant's attributes as matching criteria
        # This handles cases where Odoo only created variants for attributes with multiple values
        # and skipped single-value attributes that don't create meaningful variants
        
        print(f"Checking variant {variant_id}: stored_attrs={stored_attribute_dict}")
        print(f"  Product attributes available: {product_attributes}")
        
        # HANDLE SIMPLE PRODUCTS (no attributes)
        if not stored_attribute_dict:
            print(f"Found simple product match (no attributes): {variant_id}")
            return variant_id
        
        # STORED-ATTRIBUTE-DRIVEN MATCHING:
        # Check if product has matching values for ALL attributes that the stored variant has
        attributes_match = True
        matches_found = 0
        
        for stored_attr, stored_value in stored_attribute_dict.items():
            # Convert stored attribute name to our internal format and find corresponding product value
            product_value = _find_product_attribute_value(stored_attr, product_attributes)
            
            if not product_value:
                print(f"Product missing attribute that stored variant requires: {stored_attr}")
                attributes_match = False
                break
            elif not _attribute_values_match(product_value, stored_value):
                print(f"Attribute value mismatch: {stored_attr} product='{product_value}' stored='{stored_value}'")
                attributes_match = False
                break
            else:
                print(f"  ✓ {stored_attr}: '{product_value}' matches '{stored_value}'")
                matches_found += 1
        
        if attributes_match and matches_found == len(stored_attribute_dict):
            print(f"✅ Found stored-attribute-driven match: {variant_id}")
            print(f"  Matched {matches_found}/{len(stored_attribute_dict)} stored attributes")
            print(f"  Stored: {stored_attribute_dict}")
            return variant_id
    
    print(f"No exact match found for template: {template_name}, attributes: {product_attributes}")
    return None


def _find_product_attribute_value(stored_attr_name: str, product_attributes: Dict[str, Any]) -> Optional[str]:
    """
    Find the product attribute value that corresponds to a stored variant attribute.
    Handles the mapping between Odoo attribute names and our internal attribute names.
    
    Args:
        stored_attr_name: The attribute name from the stored variant (e.g., "flavor", "nicotine level")
        product_attributes: Dictionary of product attributes with internal names
        
    Returns:
        The product's value for the corresponding attribute, or None if not found
    """
    
    stored_attr_lower = stored_attr_name.lower().strip()
    
    # Direct mapping attempts first
    if stored_attr_lower in product_attributes:
        value = product_attributes[stored_attr_lower]
        return str(value) if value is not None else None
    
    # Handle common attribute name variations
    attribute_mappings = {
        'flavor': ['flavor'],
        'nicotine level': ['nicotine_mg', 'nicotine', 'nicotine_level'],
        'color': ['color'],
        'resistance': ['resistance_ohm', 'resistance', 'ohm'],
        'size': ['volume_ml', 'volume', 'size'],
        'coil type': ['coil_type', 'coil_model', 'model'],
        'brand': ['brand']
    }
    
    # Try to find a mapping
    for odoo_attr, internal_variations in attribute_mappings.items():
        if stored_attr_lower == odoo_attr:
            # Found the Odoo attribute, now look for any of its internal variations
            for internal_attr in internal_variations:
                if internal_attr in product_attributes:
                    value = product_attributes[internal_attr]
                    return str(value) if value is not None else None
    
    # If no direct mapping found, try fuzzy matching
    for product_attr, product_value in product_attributes.items():
        product_attr_lower = str(product_attr).lower()
        
        # Check for partial matches
        if stored_attr_lower in product_attr_lower or product_attr_lower in stored_attr_lower:
            return str(product_value) if product_value is not None else None
    
    return None


def _attribute_values_match(expected_value: str, stored_value: str) -> bool:
    """Check if two attribute values match using various strategies."""
    
    if not expected_value or not stored_value:
        return False
    
    expected_lower = str(expected_value).lower().strip()
    stored_lower = str(stored_value).lower().strip()
    
    # Exact match
    if expected_lower == stored_lower:
        return True
    
    # Numeric matching for nicotine levels (3 matches 3, 3.0, etc.)
    if expected_lower.replace('.', '').replace('mg', '').isdigit() and stored_lower.replace('.', '').replace('mg', '').isdigit():
        expected_num = float(expected_lower.replace('mg', ''))
        stored_num = float(stored_lower.replace('mg', ''))
        if expected_num == stored_num:
            return True
    
    # Substring matching
    if expected_lower in stored_lower or stored_lower in expected_lower:
        return True
    
    return False


def _convert_to_odoo_attribute_name(attr_name: str) -> str:
    """Convert internal attribute names to Odoo format using the same mapping as attribute_builder."""
    
    # Use the same attribute variations mapping as in attribute_builder.py
    attr_variations = {
        'nicotine level': ['nicotine', 'nicotine_mg', 'nicotine strength', 'nicotine_mg_range', 'nicotine_mg_min', 'nicotine_mg_max'],
        'flavor': ['flavor'],
        'brand': ['brand'],
        'color': ['color'],
        'resistance': ['resistance', 'resistance_ohm', 'ohm'],
        'size': ['volume', 'volume_ml', 'capacity'],
        'coil type': ['coil_type', 'coil model', 'coil_model']
    }
    
    attr_name_lower = attr_name.lower()
    
    # Find which Odoo attribute name this maps to
    for odoo_name, variations in attr_variations.items():
        if attr_name_lower in variations:
            return odoo_name
    
    # If no mapping found, return the original name
    return attr_name.lower()


def _get_top_variant_attributes(product_attributes: Dict[str, Any], max_attributes: int = 2) -> Dict[str, str]:
    """
    Get the top N attributes from product using the same priority system as Template Builder.
    This ensures we match on the same attributes that were used to create the existing variants.
    """
    
    # Use the exact same attribute priorities as Template Builder
    attribute_priorities = {
        'flavor': 10,           # Highest priority - customer choice
        'nicotine_mg': 9,       # High priority - customer choice  
        'resistance_ohm': 8,    # Hardware spec - customer choice
        'coil_type': 7,         # Hardware spec - customer choice
        'color': 6,             # Visual choice
        'model': 5,             # Hardware model (for coils)
        'coil_model': 5,        # Hardware model (alternative)
    }
    
    # Filter to only allowed attributes that exist in the product
    available_attributes = []
    for attr_name, attr_value_raw in product_attributes.items():
        if attr_name in attribute_priorities:
            attr_value = str(attr_value_raw) if attr_value_raw is not None else ""
            if attr_value.strip():  # Only include if has a value
                priority = attribute_priorities[attr_name]
                available_attributes.append((attr_name, priority, attr_value))
    
    # Sort by priority (descending) - same logic as Template Builder
    available_attributes.sort(key=lambda x: -x[1])
    
    # Take only the top N attributes and convert to Odoo format
    expected_attributes = {}
    for attr_name, priority, attr_value in available_attributes[:max_attributes]:
        # Convert internal attribute names to Odoo format
        odoo_attr_name = _convert_to_odoo_attribute_name(attr_name).lower()
        expected_attributes[odoo_attr_name] = attr_value
    
    return expected_attributes


def _templates_match_fuzzy(template1: str, template2: str) -> bool:
    """Check if two template names match using fuzzy logic."""
    
    # Convert to strings and handle None values
    template1_str = str(template1) if template1 is not None else ""
    template2_str = str(template2) if template2 is not None else ""
    
    # Simple fuzzy matching - check if they share significant overlap
    words1 = set(template1_str.split())
    words2 = set(template2_str.split())
    
    if len(words1) == 0 or len(words2) == 0:
        return False
    
    overlap = len(words1.intersection(words2))
    similarity = overlap / min(len(words1), len(words2))
    
    return similarity >= 0.7


