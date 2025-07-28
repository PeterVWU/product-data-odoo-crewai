import json
from pathlib import Path
from crewai.tools import tool
from typing import Dict, Any, List


@tool
def batch_llm_parser_tool(unclear_products_file: str, output_file: str, batch_size: int = 20) -> Dict[str, Any]:
    """
    Process unclear products in batches using LLM reasoning, then save all results.
    
    Args:
        unclear_products_file: Path to JSON file with unclear products
        output_file: Path to save the LLM parsing results
        batch_size: Number of products to process per batch (default: 20)
        
    Returns:
        Dict with processing status, statistics, and batch information
    """
    try:
        # Load unclear products
        with open(unclear_products_file, 'r') as f:
            unclear_products = json.load(f)
        
        total_products = len(unclear_products)
        total_batches = (total_products + batch_size - 1) // batch_size  # Ceiling division
        all_results = []
        
        print(f"Processing {total_products} unclear products in {total_batches} batches of {batch_size}")
        
        # Process in batches
        for batch_num in range(total_batches):
            start_idx = batch_num * batch_size
            end_idx = min(start_idx + batch_size, total_products)
            batch_products = unclear_products[start_idx:end_idx]
            
            print(f"Processing batch {batch_num + 1}/{total_batches} (products {start_idx + 1}-{end_idx})")
            
            # Create batch prompt
            batch_text = "\\n".join([
                f"{i+1}. Index {p['index']}: {p['name']}" 
                for i, p in enumerate(batch_products)
            ])
            
            batch_prompt = f"""Parse these {len(batch_products)} product names into structured attributes. These are products that failed regex parsing.

For e-liquids: Extract product_name (base product line), flavor, nicotine_mg, volume_ml
For hardware (coils, pods, kits, devices): Extract product_name, set flavor=null, nicotine_mg=null, volume_ml=null

Products to parse:
{batch_text}

Return a JSON array with exactly {len(batch_products)} objects, one per product, in the same order. Include the original index for each product.

Example format:
[
  {{"index": 90, "product_name": "7DZE - 7Daze (LIQ FB)(60mL) Reds", "flavor": "Fruit Mix Iced", "nicotine_mg": 12, "volume_ml": 60}},
  {{"index": 91, "product_name": "7DZE - 7Daze (LIQ FB)(60mL) Reds", "flavor": "Guava", "nicotine_mg": 12, "volume_ml": 60}}
]

JSON array for batch {batch_num + 1}:"""

            try:
                # Simulate LLM processing - in real implementation, this would call the LLM
                # For now, create structured results based on product patterns
                batch_results = []
                for product in batch_products:
                    # Create a basic parsed result (this would be replaced by actual LLM call)
                    parsed = _parse_product_with_llm_simulation(product)
                    batch_results.append(parsed)
                
                all_results.extend(batch_results)
                print(f"Batch {batch_num + 1} completed: {len(batch_results)} products processed")
                
            except Exception as e:
                print(f"Error processing batch {batch_num + 1}: {e}")
                # Continue with next batch even if this one fails
                continue
        
        # Save all results to output file
        output_path = Path(output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_file, 'w') as f:
            json.dump(all_results, f, indent=2)
        
        return {
            "status": "success",
            "total_products": total_products,
            "processed_products": len(all_results),
            "total_batches": total_batches,
            "batch_size": batch_size,
            "output_file": str(output_file),
            "success_rate": f"{len(all_results)}/{total_products} ({100*len(all_results)/total_products:.1f}%)"
        }
        
    except Exception as e:
        return {
            "status": "failed",
            "error": str(e)
        }


def _parse_product_with_llm_simulation(product: Dict) -> Dict:
    """
    Simulate LLM parsing for demonstration. In real implementation, 
    this would be replaced with actual LLM API call.
    """
    name = product['name']
    index = product['index']
    
    # Basic pattern matching as simulation (replace with real LLM call)
    result = {
        "index": index,
        "product_name": None,
        "flavor": None,
        "nicotine_mg": None,
        "volume_ml": None
    }
    
    # Simple parsing simulation - extract basic patterns
    import re
    
    # Extract nicotine (e.g., "12mg", "03mg", "25mg")
    nicotine_match = re.search(r'(\\d+)mg', name)
    if nicotine_match:
        result["nicotine_mg"] = int(nicotine_match.group(1))
    
    # Extract volume (e.g., "(60mL)", "(100mL)", "30mL")
    volume_match = re.search(r'(\\d+)mL', name)
    if volume_match:
        result["volume_ml"] = int(volume_match.group(1))
    
    # Try to extract product name and flavor from complex patterns
    if " - " in name:
        parts = name.split(" - ")
        if len(parts) >= 2:
            # First part is usually product line
            result["product_name"] = parts[0] + " - " + parts[1] if len(parts) > 2 else parts[0]
            
            # Try to extract flavor from remaining parts
            if len(parts) >= 3:
                flavor_part = parts[2]
                # Remove nicotine and volume info from flavor
                flavor_part = re.sub(r'\\s*\\d+mg.*$', '', flavor_part)
                flavor_part = re.sub(r'\\s*\\(.*?\\)', '', flavor_part)
                flavor_part = re.sub(r'\\s*\\(Discontinued\\)', '', flavor_part)
                if flavor_part.strip():
                    result["flavor"] = flavor_part.strip()
    
    # If still no product name, use first part before nicotine/volume
    if not result["product_name"]:
        clean_name = re.sub(r'\\s*\\d+mg.*$', '', name)
        clean_name = re.sub(r'\\s*\\(Discontinued\\)', '', clean_name)
        result["product_name"] = clean_name.strip()
    
    # Hardware products detection (no flavor/nicotine)
    hardware_keywords = ['Device', 'Kit', 'Coil', 'Pod', 'Mod', 'Tank', 'Atomizer', 'Battery']
    if any(keyword.lower() in name.lower() for keyword in hardware_keywords):
        result["flavor"] = None
        result["nicotine_mg"] = None
    
    return result