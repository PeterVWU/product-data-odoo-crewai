#!/usr/bin/env python3

import json
import sys
sys.path.append('src')
from product_data_odoo.tools.variant_builder import _combine_product_data, _parse_template_export, _find_matching_template, _find_template_value_combination

# Load data
with open('output/parsed/parsed_results.json', 'r') as f:
    clear_products = json.load(f)

with open('output/llm/llm_parsed_results.json', 'r') as f:
    llm_products = json.load(f)

# Combine data
combined = _combine_product_data(clear_products, llm_products)

# Parse templates
template_data = _parse_template_export('src/product_data_odoo/odoo_product_template.csv')

# Find a test product with attributes
test_product = None
for product in combined:
    attrs = product.get('attributes', {})
    if attrs and 'flavor' in attrs and 'nicotine_mg' in attrs:
        test_product = product
        break

if test_product:
    print(f"Test Product: {test_product.get('product_name')}")
    print(f"Attributes: {test_product.get('attributes')}")
    print()
    
    # Try template matching
    matching_template = _find_matching_template(test_product, template_data)
    if matching_template:
        print(f"✅ Found template: {matching_template.get('template_name')}")
        print(f"Template attributes: {list(matching_template.get('attribute_values', {}).keys())}")
        
        # Try value combination matching
        value_ids = _find_template_value_combination(test_product, matching_template)
        if value_ids:
            print(f"✅ Found {len(value_ids)} value combinations: {value_ids}")
        else:
            print("❌ No value combinations found")
            
            # Debug the attribute matching
            product_attributes = test_product.get('attributes', {})
            template_values = matching_template.get('attribute_values', {})
            
            print(f"\nDebugging attribute matching:")
            for attr_name, value_mapping in template_values.items():
                print(f"\nTemplate attribute: '{attr_name}'")
                print(f"Template values: {list(value_mapping.keys())[:5]}...")
                
                # Check if we can match this attribute
                attr_name_normalized = attr_name.lower().strip()
                product_value = None
                
                if attr_name_normalized in product_attributes:
                    product_value = product_attributes[attr_name_normalized]
                    print(f"Direct match: product has '{attr_name_normalized}' = '{product_value}'")
                elif attr_name_normalized == 'flavor' and 'flavor' in product_attributes:
                    product_value = product_attributes['flavor']
                    print(f"Flavor match: product has 'flavor' = '{product_value}'")
                elif 'nicotine' in attr_name_normalized and 'nicotine_mg' in product_attributes:
                    product_value = product_attributes['nicotine_mg']
                    print(f"Nicotine match: product has 'nicotine_mg' = '{product_value}' for template '{attr_name}'")
                elif attr_name_normalized == 'nicotine level' and 'nicotine_mg' in product_attributes:
                    product_value = product_attributes['nicotine_mg']
                    print(f"Nicotine level match: product has 'nicotine_mg' = '{product_value}'")
                else:
                    print(f"No match for template attribute '{attr_name}'")
                    
                if product_value is not None:
                    product_value_str = str(product_value).strip()
                    if product_value_str in value_mapping:
                        print(f"✅ Value '{product_value_str}' found exactly in template")
                    else:
                        print(f"❌ Value '{product_value_str}' NOT found in template")
                        print(f"   Available values: {list(value_mapping.keys())}")
    else:
        print("❌ No matching template found")
else:
    print("No test product found with flavor and nicotine_mg")