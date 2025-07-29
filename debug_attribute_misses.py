#!/usr/bin/env python3

import json

# Load the data files
with open('output/parsed/parsed_results.json', 'r') as f:
    clear_products = json.load(f)

with open('output/llm/llm_parsed_results.json', 'r') as f:
    llm_products = json.load(f)

# Create index map for LLM products
llm_by_index = {}
for product in llm_products:
    index = product.get('index')
    if index is not None:
        llm_by_index[index] = product

# Analyze products that would fail template matching
missing_product_name_count = 0
has_product_name_but_empty_attrs = 0
samples_missing_name = []
samples_empty_attrs = []

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
    
    # Check if product_name is missing or null
    if not product_name or product_name is None:
        missing_product_name_count += 1
        if len(samples_missing_name) < 5:
            samples_missing_name.append({
                'index': index,
                'original_name': final_product.get('name', 'Unknown'),
                'source': source,
                'sku': final_product.get('sku', 'No SKU')
            })
    else:
        # Has product name - check if it has attributes
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
        
        # If no attributes, this could be an attribute miss
        if not attributes:
            has_product_name_but_empty_attrs += 1
            if len(samples_empty_attrs) < 10:
                samples_empty_attrs.append({
                    'index': index,
                    'product_name': product_name,
                    'source': source,
                    'sku': final_product.get('sku', 'No SKU')
                })

print(f"Analysis Results:")
print(f"==================")
print(f"Products missing product_name: {missing_product_name_count}")
print(f"Products with product_name but no attributes: {has_product_name_but_empty_attrs}")
print(f"Total processed: {len(clear_products)}")

print(f"\nSample products missing product_name:")
for sample in samples_missing_name:
    print(f"  Index {sample['index']}: {sample['original_name']} (Source: {sample['source']}, SKU: {sample['sku']})")

print(f"\nSample products with name but no attributes:")
for sample in samples_empty_attrs:
    print(f"  Index {sample['index']}: {sample['product_name']} (Source: {sample['source']}, SKU: {sample['sku']})")