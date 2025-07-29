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
all_products = _combine_product_data(clear_products, llm_products)

# Parse templates
template_data = _parse_template_export('src/product_data_odoo/odoo_product_template.csv')

# Simulate the variant generation loop for a small sample
print(f"Processing {len(all_products)} products...")

variant_imports = []
generation_stats = {
    "total_products": len(all_products),
    "variants_generated": 0,
    "template_matches": 0,
    "template_misses": 0,
    "attribute_misses": 0,
    "templates_processed": len(template_data)
}

# Test with first 20 products to see what happens
for i, product in enumerate(all_products[:20]):
    print(f"\nProduct {i+1}: {product.get('product_name', 'Unknown')}")
    
    # Find matching template
    matching_template = _find_matching_template(product, template_data)
    
    if not matching_template:
        generation_stats["template_misses"] += 1
        print(f"  ❌ No template match")
        continue
    
    generation_stats["template_matches"] += 1
    print(f"  ✅ Template match: {matching_template['template_name']}")
    
    # Find matching attribute value combination
    template_value_ids = _find_template_value_combination(product, matching_template)
    
    if not template_value_ids:
        generation_stats["attribute_misses"] += 1
        print(f"  ❌ No attribute combinations")
        print(f"     Product attributes: {product.get('attributes', {})}")
        continue
    
    print(f"  ✅ Found {len(template_value_ids)} attribute combinations")
    
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
    print(f"  ✅ Variant created: SKU {sku}, Price {price}")

print(f"\nResults after 20 products:")
print(f"Variants generated: {generation_stats['variants_generated']}")
print(f"Template matches: {generation_stats['template_matches']}")
print(f"Template misses: {generation_stats['template_misses']}")
print(f"Attribute misses: {generation_stats['attribute_misses']}")

if variant_imports:
    print(f"\nFirst variant:")
    print(variant_imports[0])
else:
    print("\nNo variants generated in sample!")