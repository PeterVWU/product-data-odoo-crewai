#!/usr/bin/env python
import sys
import json
import asyncio
from pathlib import Path
import warnings

from datetime import datetime

from product_data_odoo.crew import ProductDataOdoo
from crewai import Agent, Crew, Task

warnings.filterwarnings("ignore", category=SyntaxWarning, module="pysbd")

# This main file is intended to be a way for you to run your
# crew locally, so refrain from adding unnecessary logic into this file.
# Replace with inputs you want to test with, it will automatically
# interpolate any tasks and agents information

async def run_async():
    """
    Run the crew with async batch processing for unclear products.
    """
    # Simple hardcoded flag to skip parsing for development
    SKIP_PARSING = True  # Set to False to run full pipeline
    # Define standardized base paths
    base_dir = Path("/root/development/data-cleaning/product_data_odoo")
    csv_path = str((base_dir / "src/product_data_odoo/VWU_Product_List.csv").resolve())
    
    # Define all output directories and file paths
    output_base = base_dir / "output"
    cleaned_dir = output_base / "cleaned"
    parsed_dir = output_base / "parsed" 
    llm_dir = output_base / "llm"
    final_dir = output_base / "final"
    
    inputs = {
        # Input files
        "csv_path": csv_path,
        "odoo_categories_file": str((base_dir / "src/product_data_odoo/odoo_product_category.csv").resolve()),
        "odoo_attributes_file": str((base_dir / "src/product_data_odoo/odoo_attributes.csv").resolve()),
        
        # Output directories
        "cleaned_dir": str(cleaned_dir),
        "parsed_dir": str(parsed_dir),
        "llm_dir": str(llm_dir),
        "final_dir": str(final_dir),
        "output_dir": str(output_base),  # For category mapper tool
        
        # Specific file paths for coordination
        "cleaned_csv": str(cleaned_dir / "cleaned_products.csv"),
        "unclear_products_file": str(parsed_dir / "unclear_products.json"),
        "parsed_results_file": str(parsed_dir / "parsed_results.json"),
        "llm_results_file": str(llm_dir / "llm_parsed_results.json"),
        "clear_products_file": str(parsed_dir / "parsed_results.json"),  # Use existing parsed results
        "llm_parsed_results_file": str(llm_dir / "llm_parsed_results.json"),
        
        # Final output files
        "final_templates": str(final_dir / "product_templates.csv"),
        "final_variants": str(final_dir / "product_variants.csv"),
        "final_attributes": str(final_dir / "attribute_candidates.json")
    }
    
    try:
        crew_instance = ProductDataOdoo()
        
        if not SKIP_PARSING:
            # Step 1: Run orchestrator for CSV processing and regex parsing
            orchestrator_crew = Crew(
                agents=[crew_instance.orchestrator()],
                tasks=[crew_instance.orchestrate_task()],
                verbose=True,
                memory=True
            )
            
            print("🚀 Running initial processing (CSV + Regex parsing)...")
            result = orchestrator_crew.kickoff(inputs=inputs)
            
            # Step 2: Check if unclear products exist and process them in batches
            unclear_products_file = Path(inputs["unclear_products_file"])
            if unclear_products_file.exists():
                print("📊 Loading unclear products for batch processing...")
                
                with open(unclear_products_file, 'r') as f:
                    unclear_products = json.load(f)
                
                if unclear_products:
                    print(f"🔄 Processing {len(unclear_products)} unclear products in batches of 20...")
                    
                    # Process ALL unclear products using efficient batching with pre-extracted names
                    test_products = unclear_products  # Process all 551 unclear products
                    batch_size = 20  # Since product names are pre-extracted, LLM can handle larger batches
                    
                    print(f"🔄 Processing {len(test_products)} unclear products in batches of {batch_size} with pre-extracted product names...")
                    
                    # Pre-process all products: split by last dash and create minimal input for LLM
                    processed_products = []
                    for product in test_products:
                        split_product = _split_product_name_attributes(product)
                        # Only send index and attributes_text to LLM for efficiency
                        llm_input = {
                            "index": split_product["index"],
                            "attributes_text": split_product["attributes_text"]
                        }
                        # Keep full product info for later merging
                        llm_input["_full_product"] = split_product
                        processed_products.append(llm_input)
                    
                    # Create batches of minimal LLM inputs
                    batches = []
                    for i in range(0, len(processed_products), batch_size):
                        batch = []
                        for product in processed_products[i:i + batch_size]:
                            # Only send minimal data to LLM
                            batch.append({
                                "index": product["index"], 
                                "attributes_text": product["attributes_text"]
                            })
                        batches.append(batch)
                    
                    print(f"📦 Created {len(batches)} batches with pre-extracted product names")
                    
                    # Create batch processing crew with Smart Parser
                    batch_crew = Crew(
                        agents=[crew_instance.smart_parser()],
                        tasks=[crew_instance.smart_parse_task()],
                        verbose=False,  # Reduce verbosity for efficient processing
                        memory=True
                    )
                    
                    all_parsed_results = []
                    
                    # Process each batch
                    for batch_num, batch in enumerate(batches):
                        try:
                            print(f"📋 Processing batch {batch_num + 1}/{len(batches)} ({len(batch)} products)...")
                            
                            # Create batch input
                            batch_input = {"batch": batch}
                            
                            # Process this batch
                            result = batch_crew.kickoff(inputs=batch_input)
                            
                            # Extract results and merge with product names
                            if hasattr(result, 'raw') and result.raw:
                                attribute_results = _extract_attribute_results(result.raw)
                                
                                # Merge attributes with product names
                                for attr_result in attribute_results:
                                    index = attr_result["index"]
                                    attributes = attr_result.get("attributes", {})
                                    
                                    # Find the full product info by index
                                    full_product = None
                                    for p in processed_products:
                                        if p["index"] == index:
                                            full_product = p["_full_product"]
                                            break
                                    
                                    if full_product:
                                        # Merge attributes with product name and brand
                                        merged_result = {
                                            "index": index,
                                            "brand": full_product["brand"],
                                            "product_name": full_product["product_name"]
                                        }
                                        
                                        # Add all discovered attributes
                                        merged_result.update(attributes)
                                        all_parsed_results.append(merged_result)
                                    else:
                                        print(f"⚠️ Could not find full product for index {index}")
                                
                                print(f"✅ Successfully parsed batch {batch_num + 1} - {len(attribute_results)} products")
                            else:
                                print(f"⚠️ No result for batch {batch_num + 1}")
                                # Add fallback results for all products in batch
                                for i, minimal_product in enumerate(batch):
                                    # Find the full product by index
                                    full_product = None
                                    for p in processed_products:
                                        if p["index"] == minimal_product["index"]:
                                            full_product = p["_full_product"]
                                            break
                                    
                                    if full_product:
                                        all_parsed_results.append({
                                            "index": minimal_product["index"],
                                            "brand": full_product["brand"],
                                            "product_name": full_product["product_name"]
                                        })
                            
                            # Progressive save after each batch
                            print(f"💾 Saving progress: {len(all_parsed_results)} total products processed...")
                            llm_dir.mkdir(parents=True, exist_ok=True)
                            with open(inputs["llm_results_file"], 'w') as f:
                                json.dump(all_parsed_results, f, indent=2)
                                
                        except Exception as batch_error:
                            print(f"❌ Error processing batch {batch_num + 1}: {batch_error}")
                            # Add fallback results for all products in batch
                            for product in batch:
                                all_parsed_results.append({
                                    "index": product["index"],
                                    "product_name": product["product_name"],
                                    "flavor": None,
                                    "nicotine_mg": None,
                                    "volume_ml": None
                                })
                            continue
                    
                    # Save merged results
                    print(f"💾 Saving {len(all_parsed_results)} parsed results...")
                    llm_dir.mkdir(parents=True, exist_ok=True)
                    with open(inputs["llm_results_file"], 'w') as f:
                        json.dump(all_parsed_results, f, indent=2)
                    
                    print("✅ Batch processing completed!")
        else:
            print("⏭️ Skipping CSV processing and LLM parsing (SKIP_PARSING=True)")
            # Verify that required files exist
            required_files = [
                inputs["parsed_results_file"],  # Use parsed_results.json instead of clear_products.json
                inputs["llm_parsed_results_file"]
            ]
            missing_files = []
            for file_path in required_files:
                if not Path(file_path).exists():
                    missing_files.append(file_path)
            
            if missing_files:
                print(f"❌ Missing required files when skipping parsing:")
                for file_path in missing_files:
                    print(f"   - {file_path}")
                print("🔄 Set SKIP_PARSING=False first to generate these files.")
                return
            else:
                print("✅ Found existing parsed data files")
        
        # Step 3: Run category mapping
        print("🏷️ Running category mapping...")
        category_crew = Crew(
            agents=[crew_instance.orchestrator()],
            tasks=[crew_instance.category_mapping_task()],
            verbose=True
        )
        
        category_result = category_crew.kickoff(inputs=inputs)
        print("✅ Category mapping completed!")
        
        # Step 4: Run attribute building
        print("🏗️ Running attribute building...")
        attribute_crew = Crew(
            agents=[crew_instance.orchestrator()],
            tasks=[crew_instance.attribute_building_task()],
            verbose=True
        )
        
        attribute_result = attribute_crew.kickoff(inputs=inputs)
        print("✅ Attribute building completed!")
        
        # Step 5: Run final merger
        print("🔄 Running final product merger...")
        merger_crew = Crew(
            agents=[crew_instance.orchestrator()],
            tasks=[Task(
                description="Merge regex parsing results with LLM parsing results using the product_merger_tool",
                agent=crew_instance.orchestrator(),
                expected_output="Final merged product data files"
            )],
            verbose=True
        )
        
        merger_crew.kickoff(inputs=inputs)
        print("🎉 Pipeline completed successfully!")
        
    except Exception as e:
        raise Exception(f"An error occurred while running the crew: {e}")

def _split_product_name_attributes(product: dict) -> dict:
    """Split product name into brand, product_name (brand + name), and attributes_text"""
    original_name = product["name"]
    
    # Find the first occurrence of " - " (dash with spaces) to extract brand
    first_dash_pos = original_name.find(" - ")
    
    if first_dash_pos == -1:
        # No dash found - use whole name as product_name, no brand or attributes
        brand = None
        product_name = original_name
        attributes_text = ""
    else:
        # Extract brand (before first dash)
        brand = original_name[:first_dash_pos].strip()
        
        # Find the last occurrence of " - " (dash with spaces) for attributes
        last_dash_pos = original_name.rfind(" - ")
        
        if last_dash_pos == first_dash_pos:
            # Only one dash found - no attributes, everything after first dash is name
            name_part = original_name[first_dash_pos + 3:].strip()  # +3 to skip " - "
            product_name = f"{brand} - {name_part}"
            attributes_text = ""
        else:
            # Multiple dashes - split by last dash for attributes
            name_part = original_name[first_dash_pos + 3:last_dash_pos].strip()
            product_name = f"{brand} - {name_part}"
            attributes_text = original_name[last_dash_pos + 3:].strip()  # +3 to skip " - "
    
    # Create new product dict with split information
    return {
        "index": product["index"],
        "name": original_name,  # Keep original for reference
        "brand": brand,
        "product_name": product_name,
        "attributes_text": attributes_text,
        "regex_result": product["regex_result"]
    }

def _extract_attribute_results(result_text: str) -> list:
    """Extract attribute parsing results from agent output"""
    import json
    import re
    
    try:
        # Try to extract JSON array from the result text
        json_match = re.search(r'\[[\s\S]*\]', result_text)
        if json_match:
            json_text = json_match.group(0)
            parsed_data = json.loads(json_text)
            print(f"✅ Successfully parsed JSON with {len(parsed_data)} items")
            return parsed_data
        else:
            print("⚠️ No JSON array found in result text")
            return []
            
    except json.JSONDecodeError as e:
        print(f"⚠️ JSON parsing failed: {e}")
        return []
    except Exception as e:
        print(f"⚠️ Error extracting results: {e}")
        return []

def _extract_batch_results(result_text: str, batch_products: list) -> list:
    """Extract structured parsing results from agent output"""
    import json
    import re
    
    try:
        # Try to extract JSON array from the result text
        # Look for JSON array pattern in the text
        json_match = re.search(r'\[[\s\S]*\]', result_text)
        if json_match:
            json_text = json_match.group(0)
            parsed_data = json.loads(json_text)
            print(f"✅ Successfully parsed JSON with {len(parsed_data)} items")
            return parsed_data
        else:
            print("⚠️ No JSON array found in result text")
            
    except json.JSONDecodeError as e:
        print(f"⚠️ JSON parsing failed: {e}")
    except Exception as e:
        print(f"⚠️ Error extracting results: {e}")
    
    # Fallback: create basic structure for all products in batch
    print(f"🔄 Using fallback parsing for {len(batch_products)} products")
    fallback_results = []
    for product in batch_products:
        fallback_results.append({
            "index": product["index"],
            "product_name": product["name"],  # Use original name as fallback
            "flavor": None,
            "nicotine_mg": None,
            "volume_ml": None
        })
    
    return fallback_results

def run():
    """
    Wrapper function to run the async crew.
    """
    asyncio.run(run_async())


def train():
    """
    Train the crew for a given number of iterations.
    """
    inputs = {
        "topic": "AI LLMs",
        'current_year': str(datetime.now().year)
    }
    try:
        ProductDataOdoo().crew().train(n_iterations=int(sys.argv[1]), filename=sys.argv[2], inputs=inputs)

    except Exception as e:
        raise Exception(f"An error occurred while training the crew: {e}")

def replay():
    """
    Replay the crew execution from a specific task.
    """
    try:
        ProductDataOdoo().crew().replay(task_id=sys.argv[1])

    except Exception as e:
        raise Exception(f"An error occurred while replaying the crew: {e}")

def test():
    """
    Test the crew execution and returns the results.
    """
    inputs = {
        "topic": "AI LLMs",
        "current_year": str(datetime.now().year)
    }
    
    try:
        ProductDataOdoo().crew().test(n_iterations=int(sys.argv[1]), eval_llm=sys.argv[2], inputs=inputs)

    except Exception as e:
        raise Exception(f"An error occurred while testing the crew: {e}")
