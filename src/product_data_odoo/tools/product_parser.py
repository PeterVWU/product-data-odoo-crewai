import pandas as pd
import re
import json
from pathlib import Path
from crewai.tools import tool
from typing import Dict, Any, List, Tuple


def _extract_with_regex(product_name: str) -> Dict[str, Any]:
    """Extract attributes using regex patterns."""
    result = {
        'product_name': None,
        'flavor': None, 
        'nicotine_mg': None,
        'volume_ml': None,
        'confidence': 0
    }
    
    # Main pattern: [PRODUCT_NAME] - [FLAVOR] [NICOTINE]mg
    main_pattern = r'^(.+) - (.+?) (\d+)mg$'
    match = re.search(main_pattern, product_name.strip())
    
    if match:
        product_name_part = match.group(1).strip()
        flavor = match.group(2).strip()
        nicotine = int(match.group(3))
        
        result['product_name'] = product_name_part
        result['flavor'] = flavor
        result['nicotine_mg'] = nicotine
        result['confidence'] = 0.9  # High confidence for main pattern
        
        # Extract volume from product name
        volume_pattern = r'\((\d+)mL\)'
        volume_match = re.search(volume_pattern, product_name_part)
        if volume_match:
            result['volume_ml'] = int(volume_match.group(1))
            result['confidence'] = 0.95
        
    else:
        # Try alternative patterns for edge cases
        # Pattern for products without clear " - " separator
        alt_pattern = r'^(.+?)\s+(\d+)mg$'
        alt_match = re.search(alt_pattern, product_name.strip())
        if alt_match:
            prefix = alt_match.group(1).strip()
            nicotine = int(alt_match.group(2))
            result['nicotine_mg'] = nicotine
            result['confidence'] = 0.3  # Lower confidence
            
            # Try to extract volume
            volume_match = re.search(r'\((\d+)mL\)', prefix)
            if volume_match:
                result['volume_ml'] = int(volume_match.group(1))
            
            # Everything else as product name (will need LLM help to separate)
            result['product_name'] = prefix
    
    return result


def _needs_llm_help(parsed_data: Dict[str, Any]) -> bool:
    """Determine if this product needs LLM assistance."""
    return (
        parsed_data['confidence'] < 0.7 or
        parsed_data['flavor'] is None or
        parsed_data['product_name'] is None or
        (parsed_data['flavor'] and len(parsed_data['flavor'].split()) > 6)  # Very long flavor names
    )


def _batch_llm_parse(unclear_products: List[Dict], agent_llm) -> List[Dict]:
    """Use LLM to parse unclear product names in batch."""
    if not unclear_products:
        return []
    
    # Create batch prompt for efficient processing
    products_text = "\n".join([
        f"{i+1}. {p['name']}" 
        for i, p in enumerate(unclear_products)
    ])
    
    prompt = f"""Parse these product names into structured attributes. These are products that failed regex parsing, so they may have unusual formats.

For e-liquids: Extract product_name (base product line), flavor, nicotine_mg, volume_ml
For hardware (coils, pods, kits): Extract product_name, variant_description (instead of flavor), no nicotine

Products:
{products_text}

Return a JSON array with one object per product. Use null for missing values:

Examples:
- "7DZE - 7Daze Click-Mates Pods (20mg 18mL; 9mL x2) - Cherry Lime"
  → {{"product_name": "7DZE - 7Daze Click-Mates Pods (20mg 18mL; 9mL x2)", "flavor": "Cherry Lime", "nicotine_mg": 20, "volume_ml": 18}}

- "FRMX - Freemax Fireluke M Series (Coils)(5-Pack) - SS316 X1 Mesh 0.12ohm"
  → {{"product_name": "FRMX - Freemax Fireluke M Series (Coils)(5-Pack)", "flavor": "SS316 X1 Mesh 0.12ohm", "nicotine_mg": null, "volume_ml": null}}

JSON array:"""
    
    try:
        if agent_llm is None:
            # Fallback when no LLM available
            return [_create_fallback_result(p) for p in unclear_products]
            
        # Use the agent's LLM to parse
        response = agent_llm.invoke(prompt)
        
        # Parse the JSON response
        import json
        import re
        
        # Extract JSON from response (handle cases where LLM adds extra text)
        json_match = re.search(r'\[.*\]', response.content, re.DOTALL)
        if json_match:
            json_str = json_match.group(0)
            parsed_results = json.loads(json_str)
            
            # Validate we got the right number of results
            if len(parsed_results) == len(unclear_products):
                return parsed_results
            else:
                print(f"Warning: LLM returned {len(parsed_results)} results for {len(unclear_products)} products")
                # Pad or truncate to match
                while len(parsed_results) < len(unclear_products):
                    parsed_results.append(_create_fallback_result(unclear_products[len(parsed_results)]))
                return parsed_results[:len(unclear_products)]
        else:
            print("Warning: Could not extract JSON from LLM response")
            return [_create_fallback_result(p) for p in unclear_products]
            
    except Exception as e:
        print(f"Error in LLM parsing: {e}")
        # Fallback to preserving regex results when available
        return [_create_fallback_result(p) for p in unclear_products]


def _create_fallback_result(product_info: Dict) -> Dict:
    """Create fallback result preserving any regex results."""
    # If we have regex results, use them
    if 'regex_result' in product_info and product_info['regex_result']:
        regex_result = product_info['regex_result']
        return {
            'product_name': regex_result.get('product_name'),
            'flavor': regex_result.get('flavor'),
            'nicotine_mg': regex_result.get('nicotine_mg'),
            'volume_ml': regex_result.get('volume_ml')
        }
    else:
        # Complete fallback - treat whole name as product_name
        return {
            'product_name': product_info['name'],
            'flavor': None,
            'nicotine_mg': None,
            'volume_ml': None
        }


def _generate_templates_and_variants(df: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame, Dict]:
    """Generate product templates and variants tables."""
    
    # Group by product_name + volume to create templates (flavors are variants)
    df['template_key'] = df['product_name'].astype(str) + '|' + df['volume_ml'].astype(str)
    
    # Create templates (unique combinations of product_name + volume)
    templates = df.groupby('template_key').agg({
        'product_name': 'first',
        'volume_ml': 'first',
        'category': 'first',
        'price': 'mean',  # Average price for template
        'sku': 'count'    # Count variants
    }).reset_index()
    
    templates = templates.rename(columns={'sku': 'variant_count'})
    templates['template_id'] = 'TPL_' + templates.index.astype(str).str.zfill(4)
    
    # Create variants (each original product becomes a variant)
    variants = df.copy()
    variants = variants.merge(
        templates[['template_key', 'template_id']], 
        on='template_key', 
        how='left'
    )
    variants['variant_id'] = 'VAR_' + variants.index.astype(str).str.zfill(4)
    
    # Generate attribute candidates
    attributes = {
        'product_names': sorted(df['product_name'].dropna().unique().tolist()),
        'flavors': sorted(df['flavor'].dropna().unique().tolist()),
        'nicotine_strengths': sorted(df['nicotine_mg'].dropna().unique().tolist()),
        'volumes': sorted(df['volume_ml'].dropna().unique().tolist())
    }
    
    return templates, variants, attributes


@tool
def product_parser_tool(cleaned_csv_path: str, out_dir: str) -> Dict[str, Any]:
    """
    Hybrid product parser that extracts structured attributes from product names.
    Uses regex for efficiency with LLM fallback for complex cases.
    
    Args:
        cleaned_csv_path: Path to cleaned products CSV
        out_dir: Output directory for generated files
        
    Returns:
        Dict with parsing results, output files, and statistics
    """
    try:
        # Ensure output directory exists
        out_path = Path(out_dir)
        out_path.mkdir(parents=True, exist_ok=True)
        
        # Read cleaned CSV
        df = pd.read_csv(cleaned_csv_path)
        
        # Parse each product with regex
        parsed_results = []
        unclear_products = []
        
        for idx, row in df.iterrows():
            product_name = row['name']
            parsed = _extract_with_regex(product_name)
            
            if _needs_llm_help(parsed):
                unclear_products.append({
                    'index': idx,
                    'name': product_name,
                    'regex_result': parsed
                })
            
            parsed_results.append(parsed)
        
        # Note: LLM processing for unclear products will be handled by Smart Parser Agent
        # This tool returns unclear products for the Orchestrator to coordinate LLM parsing
        
        # Add parsed attributes to dataframe
        for attr in ['product_name', 'flavor', 'nicotine_mg', 'volume_ml']:
            df[attr] = [r.get(attr) for r in parsed_results]
        
        # Generate templates, variants, and attributes
        templates_df, variants_df, attributes_dict = _generate_templates_and_variants(df)
        
        # Save output files
        templates_file = out_path / "product_templates.csv"
        variants_file = out_path / "product_variants.csv"
        attributes_file = out_path / "attribute_candidates.json"
        
        templates_df.to_csv(templates_file, index=False)
        variants_df.to_csv(variants_file, index=False)
        
        with open(attributes_file, 'w') as f:
            json.dump(attributes_dict, f, indent=2)
        
        # Calculate statistics
        total_products = len(df)
        regex_success = sum(1 for r in parsed_results if r['confidence'] >= 0.7)
        llm_helped = len(unclear_products)
        
        # Save intermediate files for coordination
        unclear_file = out_path / "unclear_products.json"
        parsed_file = out_path / "parsed_results.json"
        
        with open(unclear_file, 'w') as f:
            json.dump(unclear_products, f, indent=2)
        
        with open(parsed_file, 'w') as f:
            json.dump(parsed_results, f, indent=2)
        
        return {
            "status": "success",
            "total_products": total_products,
            "regex_parsed": regex_success,
            "unclear_count": len(unclear_products),
            "templates_count": len(templates_df),
            "variants_count": len(variants_df),
            "attributes": {
                "product_names": len(attributes_dict['product_names']),
                "flavors": len(attributes_dict['flavors']),
                "nicotine_strengths": len(attributes_dict['nicotine_strengths']),
                "volumes": len(attributes_dict['volumes'])
            },
            "output_files": {
                "templates": str(templates_file),
                "variants": str(variants_file),
                "attributes": str(attributes_file),
                "unclear_products": str(unclear_file),
                "parsed_results": str(parsed_file)
            },
            "sample_templates": templates_df.head(3).to_dict('records'),
            "sample_variants": variants_df.head(3).to_dict('records')
        }
        
    except Exception as e:
        return {
            "status": "failed",
            "error": str(e)
        }