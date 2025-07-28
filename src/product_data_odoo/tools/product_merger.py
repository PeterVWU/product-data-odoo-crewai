import pandas as pd
import json
from pathlib import Path
from crewai.tools import tool
from typing import Dict, Any, List


def _merge_llm_results(parsed_results: List[Dict], unclear_products: List[Dict], llm_results: List[Dict]) -> List[Dict]:
    """Merge LLM results back into parsed results."""
    
    # Create a mapping of unclear products to their results
    llm_lookup = {}
    for unclear, llm_result in zip(unclear_products, llm_results):
        if llm_result:
            llm_lookup[unclear['index']] = llm_result
    
    # Merge results
    merged_results = parsed_results.copy()
    for unclear in unclear_products:
        idx = unclear['index']
        if idx in llm_lookup:
            llm_result = llm_lookup[idx]
            current = merged_results[idx]
            merged = {}
            
            # Smart merge: use LLM result if it has a value, otherwise keep regex
            for field in ['product_name', 'flavor', 'nicotine_mg', 'volume_ml']:
                llm_value = llm_result.get(field)
                regex_value = current.get(field)
                
                if llm_value is not None:
                    merged[field] = llm_value
                elif regex_value is not None:
                    merged[field] = regex_value
                else:
                    merged[field] = None
            
            merged['confidence'] = 0.8  # LLM assisted
            merged_results[idx] = merged
    
    return merged_results


def _regenerate_templates_and_variants(cleaned_csv_path: str, merged_results: List[Dict], out_dir: str) -> Dict[str, Any]:
    """Regenerate templates and variants with merged data."""
    
    # Read original CSV
    df = pd.read_csv(cleaned_csv_path)
    
    # Update dataframe with merged results
    for attr in ['product_name', 'flavor', 'nicotine_mg', 'volume_ml']:
        df[attr] = [r.get(attr) for r in merged_results]
    
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
    
    # Save output files
    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    
    templates_file = out_path / "product_templates.csv"
    variants_file = out_path / "product_variants.csv"
    attributes_file = out_path / "attribute_candidates.json"
    
    templates.to_csv(templates_file, index=False)
    variants.to_csv(variants_file, index=False)
    
    with open(attributes_file, 'w') as f:
        json.dump(attributes, f, indent=2)
    
    return {
        "templates_df": templates,
        "variants_df": variants,
        "attributes_dict": attributes,
        "output_files": {
            "templates": str(templates_file),
            "variants": str(variants_file),
            "attributes": str(attributes_file)
        }
    }


@tool
def product_merger_tool(cleaned_csv_path: str, parsed_results_file: str, unclear_products_file: str, llm_results_file: str, out_dir: str) -> Dict[str, Any]:
    """
    Merge LLM parsing results with regex parsing results and regenerate output files.
    
    Args:
        cleaned_csv_path: Path to cleaned products CSV
        parsed_results_file: Path to JSON file with regex parsing results
        unclear_products_file: Path to JSON file with unclear products
        llm_results_file: Path to JSON file with LLM parsing results
        out_dir: Output directory for generated files
        
    Returns:
        Dict with merged results, output files, and statistics
    """
    try:
        # Load data from files
        with open(parsed_results_file, 'r') as f:
            parsed_results = json.load(f)
        
        with open(unclear_products_file, 'r') as f:
            unclear_products = json.load(f)
            
        with open(llm_results_file, 'r') as f:
            llm_results = json.load(f)
        
        # Merge LLM results with regex results
        merged_results = _merge_llm_results(parsed_results, unclear_products, llm_results)
        
        # Regenerate templates and variants with merged data
        regenerated = _regenerate_templates_and_variants(cleaned_csv_path, merged_results, out_dir)
        
        # Calculate statistics
        total_products = len(merged_results)
        regex_success = sum(1 for r in merged_results if r.get('confidence', 0) >= 0.7)
        llm_assisted = len([r for r in merged_results if r.get('confidence', 0) == 0.8])
        
        return {
            "status": "success",
            "total_products": total_products,
            "regex_parsed": regex_success,
            "llm_assisted": llm_assisted,
            "templates_count": len(regenerated["templates_df"]),
            "variants_count": len(regenerated["variants_df"]),
            "attributes": {
                "product_names": len(regenerated["attributes_dict"]['product_names']),
                "flavors": len(regenerated["attributes_dict"]['flavors']),
                "nicotine_strengths": len(regenerated["attributes_dict"]['nicotine_strengths']),
                "volumes": len(regenerated["attributes_dict"]['volumes'])
            },
            "output_files": regenerated["output_files"],
            "sample_templates": regenerated["templates_df"].head(3).to_dict('records'),
            "sample_variants": regenerated["variants_df"].head(3).to_dict('records')
        }
        
    except Exception as e:
        return {
            "status": "failed",
            "error": str(e)
        }