"""
Template Builder Tool for generating Odoo product templates CSV.
"""

import json
import pandas as pd
import csv
from pathlib import Path
from typing import Dict, List, Set, Any
from collections import defaultdict
from crewai.tools import tool


@tool
def template_builder_tool(
    clear_products_file: str,
    llm_parsed_results_file: str,
    category_mappings_file: str,
    updated_odoo_attributes_file: str,
    existing_product_templates_file: str,
    output_dir: str,
    odoo_categories_file: str
) -> dict:
    """
    Generate Odoo product templates CSV, separating existing vs new templates.
    
    Args:
        clear_products_file: Path to clear products JSON file
        llm_parsed_results_file: Path to LLM parsed results JSON file
        category_mappings_file: Path to category mappings JSON file
        updated_odoo_attributes_file: Path to updated Odoo attributes CSV
        existing_product_templates_file: Path to existing product templates CSV
        output_dir: Directory to save template CSVs
        
    Returns:
        Dict with template generation statistics and results
    """
    
    # Load all input data
    with open(clear_products_file, 'r') as f:
        clear_products = json.load(f)
    
    with open(llm_parsed_results_file, 'r') as f:
        llm_products = json.load(f)
    
    with open(category_mappings_file, 'r') as f:
        category_mappings = json.load(f)
    
    # Load existing templates and attributes
    existing_templates = _load_existing_templates(existing_product_templates_file)
    attribute_mappings, value_mappings = _load_attribute_mappings(updated_odoo_attributes_file)
    category_external_ids = _load_category_mappings(odoo_categories_file)
    
    # Merge all products
    all_products = clear_products + llm_products
    
    # Group products by template (product_name)
    templates = _group_products_by_template(all_products, category_mappings)
    
    # Separate existing vs new templates
    existing_template_updates = []
    new_templates = []
    template_summary = {}
    
    for template_name, template_data in templates.items():
        # Generate template external ID
        template_ext_id = _generate_template_external_id(template_name)
        
        # Check if template already exists
        existing_template = _find_existing_template(template_name, existing_templates)
        
        if existing_template:
            # Update existing template with new attribute lines
            update_data = _generate_existing_template_update(
                existing_template, template_data, attribute_mappings, value_mappings
            )
            if update_data:
                existing_template_updates.extend(update_data)
            
            template_summary[template_name] = {
                'external_id': existing_template['id'],
                'status': 'existing',
                'variants_count': len(template_data['products']),
                'attributes': list(template_data['attributes'].keys()),
                'category': template_data['category']
            }
        else:
            # Create new template
            new_template_rows = _generate_new_template(
                template_name, template_ext_id, template_data, attribute_mappings, value_mappings, category_external_ids
            )
            new_templates.extend(new_template_rows)  # Use extend to add all rows
            
            template_summary[template_name] = {
                'external_id': template_ext_id,
                'status': 'new',
                'variants_count': len(template_data['products']),
                'attributes': list(template_data['attributes'].keys()),
                'category': template_data['category']
            }
    
    # Save template CSVs
    output_path = Path(output_dir) / "templates"
    output_path.mkdir(parents=True, exist_ok=True)
    
    # Save existing template updates CSV (if any)
    existing_updates_file = output_path / "existing_template_updates.csv"
    if existing_template_updates:
        with open(existing_updates_file, 'w', newline='', encoding='utf-8') as f:
            fieldnames = ['id', 'attribute_line_ids/attribute_id/id', 'attribute_line_ids/value_ids/id']
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(existing_template_updates)
    
    # Save new templates CSV (if any)
    new_templates_file = output_path / "new_templates.csv"
    if new_templates:
        with open(new_templates_file, 'w', newline='', encoding='utf-8') as f:
            fieldnames = [
                'id', 'name', 'categ_id/id', 'type', 'sale_ok',
                'list_price', 'attribute_line_ids/attribute_id/id', 
                'attribute_line_ids/value_ids/id'
            ]
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(new_templates)
    
    # Save template summary
    summary_file = output_path / "template_summary.json"
    with open(summary_file, 'w') as f:
        json.dump(template_summary, f, indent=2)
    
    return {
        'status': 'success',
        'total_templates': len(templates),
        'existing_templates': len([t for t in template_summary.values() if t['status'] == 'existing']),
        'new_templates': len([t for t in template_summary.values() if t['status'] == 'new']),
        'existing_updates_records': len(existing_template_updates),
        'new_templates_records': len(new_templates),
        'clear_products_processed': len(clear_products),
        'llm_products_processed': len(llm_products),
        'template_summary': template_summary,
        'output_files': {
            'existing_updates_csv': str(existing_updates_file) if existing_template_updates else None,
            'new_templates_csv': str(new_templates_file) if new_templates else None,
            'summary': str(summary_file)
        }
    }


def _load_existing_templates(templates_file: str) -> Dict[str, Dict]:
    """Load existing Odoo templates from CSV file."""
    existing_templates = {}
    
    try:
        df = pd.read_csv(templates_file)
        
        for _, row in df.iterrows():
            template_id = row['id'] if pd.notna(row['id']) and row['id'].strip() else None
            template_name = row['name'] if pd.notna(row['name']) and row['name'].strip() else None
            category_id = row['categ_id/id'] if pd.notna(row['categ_id/id']) else None
            attr_id = row['attribute_line_ids/attribute_id/id'] if pd.notna(row['attribute_line_ids/attribute_id/id']) else None
            
            if template_id and template_name:
                if template_name not in existing_templates:
                    existing_templates[template_name] = {
                        'id': template_id,
                        'name': template_name,
                        'category_id': category_id,
                        'attributes': set()
                    }
                
                # Add attribute to this template
                if attr_id:
                    existing_templates[template_name]['attributes'].add(attr_id)
                    
    except Exception as e:
        print(f"Warning: Could not load existing templates: {e}")
        
    return existing_templates


def _load_attribute_mappings(attributes_file: str) -> tuple[Dict[str, str], Dict[str, Dict[str, str]]]:
    """Load attribute name to external ID mappings and attribute-specific value mappings."""
    attribute_mappings = {}
    value_mappings = {}  # Structure: {attribute_name: {value_name: external_id}}
    
    try:
        df = pd.read_csv(attributes_file)
        
        current_attr_name = None
        current_attr_key = None
        for _, row in df.iterrows():
            attr_id = row['id'] if pd.notna(row['id']) and row['id'].strip() else None
            attr_name = row['name'] if pd.notna(row['name']) and row['name'].strip() else None
            value_id = row['value_ids/id'] if pd.notna(row['value_ids/id']) and row['value_ids/id'].strip() else None
            value_name = row['value_ids/name'] if pd.notna(row['value_ids/name']) and row['value_ids/name'].strip() else None
            
            if attr_id and attr_name:
                # New attribute definition
                current_attr_name = attr_name.lower()
                attribute_mappings[current_attr_name] = attr_id
                
                # Map exact attribute names only - avoid fuzzy matching confusion
                if current_attr_name == 'flavor':
                    current_attr_key = 'flavor'
                    attribute_mappings['flavor'] = attr_id
                elif current_attr_name == 'nicotine level':
                    current_attr_key = 'nicotine_mg'
                    attribute_mappings['nicotine_mg'] = attr_id
                elif current_attr_name == 'size':
                    current_attr_key = 'volume_ml'
                    attribute_mappings['volume_ml'] = attr_id
                elif current_attr_name == 'brand':
                    current_attr_key = 'brand'
                    attribute_mappings['brand'] = attr_id
                elif current_attr_name == 'color':
                    current_attr_key = 'color'
                    attribute_mappings['color'] = attr_id
                elif current_attr_name == 'resistance':
                    current_attr_key = 'resistance_ohm'
                    attribute_mappings['resistance_ohm'] = attr_id
                elif 'coil' in current_attr_name and 'model' in current_attr_name:
                    current_attr_key = 'coil_model'
                    attribute_mappings['coil_model'] = attr_id
                elif 'coil' in current_attr_name and 'type' in current_attr_name:
                    current_attr_key = 'coil_type'
                    attribute_mappings['coil_type'] = attr_id
                else:
                    current_attr_key = current_attr_name
                
                # Initialize the value mapping for this attribute
                if current_attr_key not in value_mappings:
                    value_mappings[current_attr_key] = {}
                    
            # Map attribute values to their external IDs (attribute-specific)
            if current_attr_key and value_id and value_name:
                # Store the mapping from value name to external ID for this specific attribute
                value_key = value_name.lower().strip()
                value_mappings[current_attr_key][value_key] = value_id
                    
    except Exception as e:
        print(f"Warning: Could not load attribute mappings: {e}")
        
    return attribute_mappings, value_mappings


def _load_category_mappings(categories_file: str) -> Dict[str, str]:
    """Load product category name to external ID mappings."""
    category_mappings = {}
    
    try:
        df = pd.read_csv(categories_file)
        
        for _, row in df.iterrows():
            category_id = row['id'] if pd.notna(row['id']) and row['id'].strip() else None
            category_name = row['name'] if pd.notna(row['name']) and row['name'].strip() else None
            
            if category_id and category_name:
                # Map category name to external ID
                category_mappings[category_name] = category_id
                    
    except Exception as e:
        print(f"Warning: Could not load category mappings: {e}")
        
    return category_mappings


def _group_products_by_template(products: List[Dict], category_mappings: Dict) -> Dict[str, Dict]:
    """Group products by their template (product_name)."""
    templates = defaultdict(lambda: {
        'products': [],
        'attributes': defaultdict(set),
        'prices': [],
        'category': None
    })
    
    # Create product name mapping for category lookups
    category_lookup = {item['product_name']: item['category_name'] for item in category_mappings}
    
    for product in products:
        # Use product_name as template grouping key
        template_name = product.get('product_name', product.get('name'))
        if not template_name:
            continue
            
        # Get category for this product using product_name
        category = category_lookup.get(template_name, 'Saleable')
        
        template_data = templates[template_name]
        template_data['products'].append(product)
        template_data['category'] = category  # Use last category found
        
        # Collect price if available
        if 'price' in product and product['price']:
            try:
                price = float(str(product['price']).replace('$', '').replace(',', ''))
                template_data['prices'].append(price)
            except:
                pass
        
        # Collect all attributes from this product
        _collect_template_attributes(product, template_data['attributes'])
    
    return dict(templates)


def _collect_template_attributes(product: Dict, template_attributes: Dict[str, Set]):
    """Collect all unique attributes and their values for a template."""
    
    # Standard attribute fields
    standard_attrs = ['flavor', 'nicotine_mg', 'volume_ml', 'brand', 'color', 'resistance_ohm', 'coil_model', 'coil_type']
    
    for attr_name in standard_attrs:
        if attr_name in product and product[attr_name] is not None:
            value = str(product[attr_name]).strip()
            if value:
                template_attributes[attr_name].add(value)
    
    # Check for nested attributes (from LLM parsing)
    if 'attributes' in product and isinstance(product['attributes'], dict):
        for attr_name, value in product['attributes'].items():
            if value is not None:
                value_str = str(value).strip()
                if value_str:
                    template_attributes[attr_name].add(value_str)


def _find_existing_template(template_name: str, existing_templates: Dict) -> Dict:
    """Find existing template by name (fuzzy matching)."""
    
    # Direct match
    if template_name in existing_templates:
        return existing_templates[template_name]
    
    # Fuzzy matching - look for templates that contain key parts
    template_lower = template_name.lower()
    
    for existing_name, template_data in existing_templates.items():
        existing_lower = existing_name.lower()
        
        # Check if they share significant common parts
        if _template_names_match(template_lower, existing_lower):
            return template_data
    
    return None


def _template_names_match(name1: str, name2: str) -> bool:
    """Check if two template names are likely the same product."""
    
    # Split names into words
    words1 = set(name1.replace('-', ' ').split())
    words2 = set(name2.replace('-', ' ').split())
    
    # Remove common words that don't help with matching
    common_words = {'the', 'and', 'or', 'with', 'for', 'kit', 'device', 'pack', 'ml', 'mg'}
    words1 -= common_words
    words2 -= common_words
    
    if not words1 or not words2:
        return False
    
    # Calculate overlap
    intersection = words1 & words2
    union = words1 | words2
    
    # Require at least 60% overlap and at least 2 matching words
    if len(intersection) >= 2 and len(intersection) / len(union) >= 0.6:
        return True
    
    return False


def _generate_template_external_id(template_name: str) -> str:
    """Generate External ID for a template."""
    import re
    
    # Clean the name for use as external ID
    clean_name = re.sub(r'[^a-zA-Z0-9\s\-]', '', template_name)
    clean_name = re.sub(r'\s+', '_', clean_name.strip())
    clean_name = clean_name.lower()
    
    return f"template_{clean_name}"


def _generate_existing_template_update(
    existing_template: Dict, 
    template_data: Dict, 
    attribute_mappings: Dict,
    value_mappings: Dict
) -> List[Dict]:
    """Generate CSV rows to update existing template with new attribute lines."""
    
    updates = []
    existing_attrs = existing_template.get('attributes', set())
    
    # Check each attribute in the template data
    for attr_name, attr_values in template_data['attributes'].items():
        # Get the attribute external ID
        attr_external_id = attribute_mappings.get(attr_name.lower())
        if not attr_external_id:
            continue
            
        # Skip if this attribute is already configured on the template
        if attr_external_id in existing_attrs:
            continue
            
        # Add this attribute line to the template - use actual External IDs
        value_ids = _get_value_external_ids(attr_values, attr_name, value_mappings)
        
        updates.append({
            'id': existing_template['id'],
            'attribute_line_ids/attribute_id/id': attr_external_id,
            'attribute_line_ids/value_ids/id': value_ids
        })
    
    return updates


def _generate_new_template(
    template_name: str,
    template_ext_id: str, 
    template_data: Dict,
    attribute_mappings: Dict,
    value_mappings: Dict,
    category_external_ids: Dict
) -> List[Dict]:
    """Generate CSV rows for new template with all attributes."""
    
    # Calculate average price
    prices = template_data['prices']
    avg_price = sum(prices) / len(prices) if prices else 0.0
    
    # Get category external ID
    category_ext_id = _map_category_to_external_id(template_data['category'], category_external_ids)
    
    # Generate multiple rows - one for each attribute
    template_rows = []
    
    # Prioritize attributes in order: flavor, nicotine_mg, volume_ml, then others
    attribute_priority = ['flavor', 'nicotine_mg', 'volume_ml']
    other_attributes = [attr for attr in template_data['attributes'].keys() if attr not in attribute_priority]
    all_attributes = attribute_priority + other_attributes
    
    first_row = True
    for attr_name in all_attributes:
        if attr_name in template_data['attributes']:
            attr_external_id = attribute_mappings.get(attr_name)
            if attr_external_id:
                values = template_data['attributes'][attr_name]
                value_external_ids = _get_value_external_ids(values, attr_name, value_mappings)
                
                if first_row:
                    # First row: Full template info + first attribute
                    template_rows.append({
                        'id': template_ext_id,
                        'name': template_name,
                        'categ_id/id': category_ext_id,
                        'type': 'consu',
                        'sale_ok': 'True',
                        'list_price': f"{avg_price:.2f}",
                        'attribute_line_ids/attribute_id/id': attr_external_id,
                        'attribute_line_ids/value_ids/id': value_external_ids
                    })
                    first_row = False
                else:
                    # Additional rows: Empty template fields + additional attributes
                    template_rows.append({
                        'id': '',
                        'name': '',
                        'categ_id/id': '',
                        'type': '',
                        'sale_ok': '',
                        'list_price': '',
                        'attribute_line_ids/attribute_id/id': attr_external_id,
                        'attribute_line_ids/value_ids/id': value_external_ids
                    })
    
    return template_rows


def _map_category_to_external_id(category_name: str, category_external_ids: Dict[str, str]) -> str:
    """Map category name to external ID using actual Odoo External IDs."""
    
    # First try direct lookup from the loaded category External IDs
    external_id = category_external_ids.get(category_name)
    if external_id:
        return external_id
    
    # Fallback to default Saleable category if not found
    return category_external_ids.get('Saleable', 'product.product_category_1')


def _get_value_external_ids(values: Set[str], attribute_name: str, value_mappings: Dict[str, Dict[str, str]]) -> str:
    """Convert attribute values to their External IDs, fallback to descriptive names if not found."""
    external_ids = []
    
    # Get the value mappings for this specific attribute
    attr_value_mappings = value_mappings.get(attribute_name, {})
    
    for value in sorted(values):
        # Try to find the External ID for this value in this attribute's mapping
        value_key = str(value).lower().strip()
        external_id = attr_value_mappings.get(value_key)
        
        if external_id:
            external_ids.append(external_id)
        else:
            # Fallback to descriptive name if External ID not found
            fallback_id = f"value_{_sanitize_value(value)}"
            external_ids.append(fallback_id)
            print(f"Warning: No External ID found for value '{value}' in attribute '{attribute_name}', using fallback: {fallback_id}")
    
    return ','.join(external_ids)


def _sanitize_value(value: str) -> str:
    """Sanitize a value for use in external IDs."""
    import re
    # Convert to lowercase, replace spaces and special chars with underscores
    sanitized = re.sub(r'[^a-zA-Z0-9_]', '_', str(value).lower())
    # Remove multiple consecutive underscores
    sanitized = re.sub(r'_+', '_', sanitized)
    # Remove leading/trailing underscores
    sanitized = sanitized.strip('_')
    return sanitized or 'unknown'