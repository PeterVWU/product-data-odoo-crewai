#!/usr/bin/env python3

import json
import sys
sys.path.append('src')

# Load some test data
with open('output/parsed/parsed_results.json', 'r') as f:
    products = json.load(f)

with open('output/variants/template_analysis.json', 'r') as f:
    templates = json.load(f)

# Find a product that should match
test_product = None
for product in products[:10]:
    if product.get('flavor') and product.get('nicotine_mg'):
        test_product = product
        break

if test_product:
    print(f"Test Product: {test_product.get('product_name')}")
    print(f"Flavor: {test_product.get('flavor')}")
    print(f"Nicotine: {test_product.get('nicotine_mg')}")
    print()
    
    # Try to find matching template
    product_name = test_product.get('product_name', '')
    
    for template_id, template_info in templates.items():
        template_name = template_info.get('template_name', '')
        if product_name.lower() in template_name.lower() or template_name.lower() in product_name.lower():
            print(f"Found matching template: {template_name}")
            print(f"Template attributes: {list(template_info.get('attribute_values', {}).keys())}")
            
            # Check if template has flavor and nicotine
            attr_values = template_info.get('attribute_values', {})
            if 'flavor' in attr_values:
                print(f"Template flavors: {list(attr_values['flavor'].keys())[:5]}...")
                
                # Check if our flavor is in template
                product_flavor = test_product.get('flavor', '')
                if product_flavor in attr_values['flavor']:
                    print(f"✅ Flavor '{product_flavor}' found in template")
                else:
                    print(f"❌ Flavor '{product_flavor}' NOT found in template")
                    
            if 'nicotine level' in attr_values:
                print(f"Template nicotine levels: {list(attr_values['nicotine level'].keys())}")
                
                # Check if our nicotine is in template
                product_nicotine = test_product.get('nicotine_mg', '')
                nicotine_values = attr_values['nicotine level']
                
                product_nicotine_str = str(product_nicotine)
                
                if product_nicotine_str in nicotine_values:
                    print(f"✅ Nicotine '{product_nicotine_str}' found exactly")
                elif f"{product_nicotine_str}MG" in nicotine_values:
                    print(f"✅ Nicotine '{product_nicotine_str}MG' found with MG suffix")
                else:
                    print(f"❌ Nicotine '{product_nicotine_str}' NOT found in template")
                    print(f"  Product type: {type(product_nicotine)}, Template keys: {list(nicotine_values.keys())}")
                    # Try to find close matches
                    for val in nicotine_values.keys():
                        if str(product_nicotine) in str(val) or str(val).replace('MG', '') == str(product_nicotine):
                            print(f"  Possible match: '{val}'")
            break
else:
    print("No test product found with flavor and nicotine")