"""
Category Mapper Tool for mapping products to existing Odoo categories.
"""

import json
import pandas as pd
from pathlib import Path
from typing import Dict, List, Any
from crewai.tools import tool


@tool
def category_mapper_tool(
    clear_products_file: str,
    llm_parsed_results_file: str,
    odoo_categories_file: str,
    output_dir: str
) -> dict:
    """
    Map products to existing Odoo categories based on product characteristics.
    
    Args:
        clear_products_file: Path to clear products JSON file
        llm_parsed_results_file: Path to LLM parsed results JSON file  
        odoo_categories_file: Path to Odoo categories CSV file
        output_dir: Directory to save category mapping results
        
    Returns:
        Dict with mapping statistics and results
    """
    
    # Load Odoo categories
    categories_df = pd.read_csv(odoo_categories_file)
    categories = {}
    for _, row in categories_df.iterrows():
        categories[row['name']] = {
            'id': row['id'],
            'name': row['name'],
            'parent_id': row['parent_id']
        }
    
    # Load product data
    with open(clear_products_file, 'r') as f:
        clear_products = json.load(f)
    
    with open(llm_parsed_results_file, 'r') as f:
        llm_products = json.load(f)
    
    # Create category mapping results
    category_mappings = []
    
    # Process clear products (regex parsed)
    for product in clear_products:
        category_info = _determine_category(product, categories)
        category_mappings.append({
            'source': 'regex',
            'product_name': product.get('product_name', ''),
            'original_name': product.get('name', product.get('product_name', '')),
            'category_id': category_info['id'],
            'category_name': category_info['name'],
            'mapping_reason': category_info['reason'],
            'confidence': product.get('confidence', 0.0),
            'attributes': _extract_attributes(product)
        })
    
    # Process LLM parsed products
    for product in llm_products:
        category_info = _determine_category(product, categories)
        category_mappings.append({
            'source': 'llm',
            'product_name': product.get('product_name', ''),
            'original_name': product.get('name', product.get('product_name', '')),
            'brand': product.get('brand', ''),
            'category_id': category_info['id'],
            'category_name': category_info['name'],
            'mapping_reason': category_info['reason'],
            'confidence': 1.0,  # LLM products are manually verified
            'attributes': _extract_attributes(product)
        })
    
    # Save category mappings
    output_path = Path(output_dir) / "categories"
    output_path.mkdir(parents=True, exist_ok=True)
    
    category_mappings_file = output_path / "category_mappings.json"
    with open(category_mappings_file, 'w') as f:
        json.dump(category_mappings, f, indent=2)
    
    # Generate category statistics
    category_stats = _generate_category_stats(category_mappings)
    
    stats_file = output_path / "category_stats.json"
    with open(stats_file, 'w') as f:
        json.dump(category_stats, f, indent=2)
    
    return {
        'status': 'success',
        'total_products': len(category_mappings),
        'clear_products': len(clear_products),
        'llm_products': len(llm_products),
        'category_distribution': category_stats,
        'output_files': {
            'mappings': str(category_mappings_file),
            'stats': str(stats_file)
        }
    }


def _determine_category(product: Dict[str, Any], categories: Dict[str, Dict]) -> Dict[str, str]:
    """
    Determine the best Odoo category for a product based on its characteristics.
    
    Args:
        product: Product data dictionary
        categories: Available Odoo categories
        
    Returns:
        Dict with category ID, name, and reasoning
    """
    # Handle different data structures safely
    product_name = (product.get('product_name') or '').lower()
    original_name = (product.get('name') or product.get('product_name') or '').lower()
    
    # Handle attributes - can be nested dict or direct fields
    attributes = product.get('attributes', {}) if isinstance(product.get('attributes'), dict) else {}
    
    # Extract product characteristics safely
    has_flavor = bool(product.get('flavor') or attributes.get('flavor'))
    has_nicotine = bool(product.get('nicotine_mg') or attributes.get('nicotine_mg'))
    has_volume = bool(product.get('volume_ml') or attributes.get('volume_ml'))
    
    # Category mapping logic
    
    # 1. E-Juice Products (liquid with flavor/nicotine)
    if has_flavor and (has_nicotine or has_volume):
        if 'E-Juice' in categories:
            return {
                'id': categories['E-Juice']['id'],
                'name': 'E-Juice',
                'reason': 'Product has flavor and nicotine/volume - liquid e-juice'
            }
    
    # 2. Hardware Products
    # Coils
    if any(keyword in product_name or keyword in original_name for keyword in ['coil', 'mesh', 'ohm']):
        if 'Coil' in categories:
            return {
                'id': categories['Coil']['id'],
                'name': 'Coil',
                'reason': 'Product contains coil/mesh/ohm keywords'
            }
    
    # Disposables
    if any(keyword in product_name or keyword in original_name for keyword in ['disposable', 'puff', 'device only']):
        if 'Disposable' in categories:
            return {
                'id': categories['Disposable']['id'],
                'name': 'Disposable',
                'reason': 'Product contains disposable/puff/device keywords'
            }
    
    # Pods/Cartridges
    if any(keyword in product_name or keyword in original_name for keyword in ['pod', 'cartridge', 'cart']):
        if 'Replacement Pod' in categories:
            return {
                'id': categories['Replacement Pod']['id'],
                'name': 'Replacement Pod',
                'reason': 'Product contains pod/cartridge keywords'
            }
    
    # Kits/Mods
    if any(keyword in product_name or keyword in original_name for keyword in ['kit', 'mod', 'starter']):
        if 'Kit' in categories:
            return {
                'id': categories['Kit']['id'],
                'name': 'Kit',
                'reason': 'Product contains kit/mod keywords'
            }
    
    # Batteries
    if any(keyword in product_name or keyword in original_name for keyword in ['battery', 'batt', 'mah']):
        if 'Battery' in categories:
            return {
                'id': categories['Battery']['id'],
                'name': 'Battery',
                'reason': 'Product contains battery keywords'
            }
    
    # Chargers
    if any(keyword in product_name or keyword in original_name for keyword in ['charger', 'charging', 'usb']):
        if 'Chargers' in categories:
            return {
                'id': categories['Chargers']['id'],
                'name': 'Chargers',
                'reason': 'Product contains charger keywords'
            }
    
    # Tanks
    if any(keyword in product_name or keyword in original_name for keyword in ['tank', 'atomizer']):
        if 'Tank' in categories:
            return {
                'id': categories['Tank']['id'],
                'name': 'Tank',
                'reason': 'Product contains tank keywords'
            }
    
    # 3. Brand-based fallback for unclear products
    brand = (product.get('brand') or '').lower()
    if brand:
        # Most e-liquid brands should go to E-Juice
        eliquid_brands = ['7dze', '7daze', 'naked', 'twist', 'juice', 'liquid', 'vape']
        if any(brand_keyword in brand for brand_keyword in eliquid_brands):
            if 'E-Juice' in categories:
                return {
                    'id': categories['E-Juice']['id'],
                    'name': 'E-Juice',
                    'reason': f'Brand "{brand}" typically produces e-liquid'
                }
    
    # 4. Default fallback to Saleable
    if 'Saleable' in categories:
        return {
            'id': categories['Saleable']['id'],
            'name': 'Saleable',
            'reason': 'Default category - no specific match found'
        }
    
    # 5. Ultimate fallback (shouldn't happen)
    return {
        'id': 'product.product_category_1',
        'name': 'Saleable',
        'reason': 'Hardcoded fallback'
    }


def _extract_attributes(product: Dict[str, Any]) -> Dict[str, Any]:
    """Extract all available attributes from a product."""
    attributes = {}
    
    # Standard attributes
    for attr in ['flavor', 'nicotine_mg', 'volume_ml', 'brand']:
        if attr in product and product[attr] is not None:
            attributes[attr] = product[attr]
    
    # LLM-parsed attributes (nested)
    if 'attributes' in product and isinstance(product['attributes'], dict):
        attributes.update(product['attributes'])
    
    return attributes


def _generate_category_stats(mappings: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Generate statistics about category distribution."""
    stats = {
        'total_products': len(mappings),
        'by_category': {},
        'by_source': {'regex': 0, 'llm': 0},
        'mapping_reasons': {}
    }
    
    for mapping in mappings:
        # Category distribution
        category = mapping['category_name']
        if category not in stats['by_category']:
            stats['by_category'][category] = 0
        stats['by_category'][category] += 1
        
        # Source distribution
        source = mapping['source']
        stats['by_source'][source] += 1
        
        # Mapping reason distribution
        reason = mapping['mapping_reason']
        if reason not in stats['mapping_reasons']:
            stats['mapping_reasons'][reason] = 0
        stats['mapping_reasons'][reason] += 1
    
    return stats