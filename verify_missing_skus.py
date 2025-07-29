#!/usr/bin/env python3

import json
import pandas as pd

# Load the data files
with open('output/parsed/parsed_results.json', 'r') as f:
    clear_products = json.load(f)

with open('output/llm/llm_parsed_results.json', 'r') as f:
    llm_products = json.load(f)

# Load the templates CSV to get SKUs that are already in templates
try:
    templates_df = pd.read_csv('output/templates/new_templates.csv')
    template_skus = set(templates_df['default_code'].dropna().tolist())
    print(f"Found {len(template_skus)} SKUs in new_templates.csv")
except Exception as e:
    print(f"Error loading new_templates.csv: {e}")
    template_skus = set()

# Load generated variants to get SKUs that were successfully converted to variants
try:
    variants_df = pd.read_csv('output/variants/product_variant_import.csv')
    variant_skus = set(variants_df['default_code'].dropna().tolist())
    print(f"Found {len(variant_skus)} SKUs in product_variant_import.csv")
except Exception as e:
    print(f"Error loading product_variant_import.csv: {e}")
    variant_skus = set()

# Create index map for LLM products
llm_by_index = {}
for product in llm_products:
    index = product.get('index')
    if index is not None:
        llm_by_index[index] = product

# Find products that failed variant generation (no attributes)
failed_variant_products = []
all_product_skus = set()

for i, product in enumerate(clear_products):
    index = product.get('index', i)
    
    # Use LLM result if available, otherwise regex result
    if index in llm_by_index:
        final_product = llm_by_index[index]
        source = 'llm'
    else:
        final_product = product
        source = 'regex'
    
    product_name = final_product.get('product_name', '')
    sku = final_product.get('sku', '')
    
    all_product_skus.add(sku)
    
    # Check if this product has proper name but no attributes (would fail variant generation)
    if product_name and product_name is not None:
        attributes = {}
        
        # Check for attributes from LLM
        if source == 'llm':
            for attr_name in ['flavor', 'nicotine_mg', 'volume_ml', 'color', 'resistance_ohm', 'coil_type']:
                if attr_name in final_product and final_product[attr_name] is not None:
                    attributes[attr_name] = str(final_product[attr_name])
            
            if 'attributes' in final_product and isinstance(final_product['attributes'], dict):
                for key, value in final_product['attributes'].items():
                    if key not in ['index', 'brand', 'product_name', 'name', 'sku', 'price'] and value is not None:
                        attributes[key] = str(value)
        else:
            # Regex attributes
            if 'flavor' in final_product and final_product['flavor'] is not None:
                attributes['flavor'] = str(final_product['flavor'])
            if 'nicotine_mg' in final_product and final_product['nicotine_mg'] is not None:
                attributes['nicotine_mg'] = str(final_product['nicotine_mg'])
            if 'volume_ml' in final_product and final_product['volume_ml'] is not None:
                attributes['volume_ml'] = str(final_product['volume_ml'])
        
        # If no attributes, this would fail variant generation
        if not attributes:
            failed_variant_products.append({
                'sku': sku,
                'product_name': product_name,
                'source': source
            })

print(f"\nAnalysis Results:")
print(f"==================")
print(f"Total products processed: {len(clear_products)}")
print(f"Products that failed variant generation (no attributes): {len(failed_variant_products)}")
print(f"SKUs in template file: {len(template_skus)}")
print(f"SKUs in variant file: {len(variant_skus)}")

# Check if failed variant SKUs are in templates
failed_skus = set(p['sku'] for p in failed_variant_products)
skus_in_templates = failed_skus.intersection(template_skus)
skus_missing_from_templates = failed_skus - template_skus

print(f"\nSKU Coverage Analysis:")
print(f"======================")
print(f"Failed variant SKUs: {len(failed_skus)}")
print(f"Found in templates: {len(skus_in_templates)} ({len(skus_in_templates)/len(failed_skus)*100:.1f}%)")
print(f"Missing from templates: {len(skus_missing_from_templates)} ({len(skus_missing_from_templates)/len(failed_skus)*100:.1f}%)")

if skus_missing_from_templates:
    print(f"\nSKUs missing from templates (first 10):")
    for sku in list(skus_missing_from_templates)[:10]:
        product_info = next((p for p in failed_variant_products if p['sku'] == sku), None)
        if product_info:
            print(f"  {sku}: {product_info['product_name']}")

print(f"\nSKU Distribution:")
print(f"==================")
print(f"Total unique SKUs in data: {len(all_product_skus)}")
print(f"SKUs converted to variants: {len(variant_skus)}")
print(f"SKUs in templates (simple products): {len(template_skus)}")
print(f"Coverage: {(len(variant_skus) + len(template_skus))/len(all_product_skus)*100:.1f}%")