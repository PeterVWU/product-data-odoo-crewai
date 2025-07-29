#!/usr/bin/env python3

import sys
sys.path.append('src')

# Import the actual tool
from product_data_odoo.tools.variant_builder import variant_builder_tool

# Test with the exact same parameters as CrewAI would use
try:
    result = variant_builder_tool.func(
        clear_products_file='output/parsed/parsed_results.json',
        llm_parsed_results_file='output/llm/llm_parsed_results.json', 
        odoo_product_template_file='src/product_data_odoo/odoo_product_template.csv',
        output_dir='output'
    )
    
    print("Tool executed successfully!")
    print(f"Result: {result}")
    
except Exception as e:
    print(f"Error occurred: {e}")
    import traceback
    traceback.print_exc()