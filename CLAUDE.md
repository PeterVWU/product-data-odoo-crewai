# Product Data Odoo - CrewAI Project

## Overview
This is a CrewAI-based data cleaning and processing pipeline that converts vendor CSV files into Odoo-ready import files for e-liquid product data. The system uses a hybrid approach combining deterministic data processing tools with AI agents for complex parsing tasks.

## Architecture (Option C: Hybrid Intelligence)

### 🤖 AI Agents (2 Total)
1. **Orchestrator Agent** - Project manager with reasoning capabilities
   - Controls workflow and decision-making
   - Manages human approval checkpoints
   - Evaluates data quality and makes routing decisions
   
2. **Smart Parser Agent** - Product name intelligence
   - Handles complex product name parsing requiring reasoning
   - Processes edge cases and non-standard formats (15% of products)
   - Adapts to new vendor formats and product types

### 🔧 Processing Tools (6 Total - Deterministic)
All tools use `@tool` decorator and focus on fast, token-efficient processing:

1. **CSV Processor Tool** - Data validation and column standardization
2. **Category Mapper Tool** - Category standardization and hierarchy mapping
3. **Attribute Builder Tool** - Generate Odoo product attributes CSV
4. **Template Builder Tool** - Create product template records
5. **Variant Builder Tool** - Generate product variant records
6. **Inventory Builder Tool** - Create inventory adjustment records

## Project Structure
- **Main entry**: `src/product_data_odoo/main.py`
- **Crew definition**: `src/product_data_odoo/crew.py`
- **Configuration**: `src/product_data_odoo/config/`
  - `agents.yaml` - Agent definitions (Orchestrator + Smart Parser)
  - `tasks.yaml` - Task definitions
- **Tools**: `src/product_data_odoo/tools/`
  - `csv_processor.py` - Data cleaning and validation
  - `product_parser.py` - Hybrid regex + LLM parsing
- **Data**: `src/product_data_odoo/VWU_Product_List.csv`
- **Knowledge**: `knowledge/user_preference.txt`

## Data Flow
```
Vendor CSV → CSV Processor Tool → Smart Parser Agent → 
Category Mapper Tool → Attribute Builder Tool → 
Template Builder Tool → Variant Builder Tool → 
Inventory Builder Tool → Orchestrator Approval → 
Ready-to-Import Odoo CSV Files
```

## Parsing Strategy (Hybrid Approach)
- **85% Regex Processing**: Fast pattern matching for standard formats
  - Pattern: `[PRODUCT_NAME] - [FLAVOR] [NICOTINE]mg`
  - Example: "7DZE - 7Daze Fusion TFN - Banana Cantaloupe 03mg"
- **15% AI Processing**: LLM reasoning for complex cases (551 products)
  - Three-part parsing: `[BRAND] - [PRODUCT_NAME] - [ATTRIBUTES]`
  - Concurrent processing using CrewAI's `kickoff_for_each_async`
  - Smart attribute extraction without rigid schema enforcement
  - Token-efficient: Only attributes_text sent to LLM for parsing
  - Quality: 85.5% completion rate with consistent product naming

## Advanced Parsing Implementation

### Three-Part Product Name Parsing
```python
def _split_product_name_attributes(product: dict) -> dict:
    """Split product name into brand, product_name (brand + name), and attributes_text"""
    original_name = product["name"]
    
    # Find first " - " for brand extraction
    first_dash_pos = original_name.find(" - ")
    
    if first_dash_pos == -1:
        # No dash found - use whole name as product_name
        brand = None
        product_name = original_name
        attributes_text = ""
    else:
        # Extract brand (before first dash)
        brand = original_name[:first_dash_pos].strip()
        
        # Find last " - " for attributes separation
        last_dash_pos = original_name.rfind(" - ")
        
        if last_dash_pos == first_dash_pos:
            # Only one dash - no attributes
            name_part = original_name[first_dash_pos + 3:].strip()
            product_name = f"{brand} - {name_part}"
            attributes_text = ""
        else:
            # Multiple dashes - split by last dash for attributes
            name_part = original_name[first_dash_pos + 3:last_dash_pos].strip()
            product_name = f"{brand} - {name_part}"
            attributes_text = original_name[last_dash_pos + 3:].strip()
    
    return {
        "index": product["index"],
        "name": original_name,
        "brand": brand,
        "product_name": product_name,
        "attributes_text": attributes_text,
        "regex_result": product["regex_result"]
    }
```

### Concurrent LLM Processing
```python
# Process all unclear products using kickoff_for_each_async
results = await self.smart_parser_crew.kickoff_for_each_async(
    inputs=batch_inputs
)

# Each batch processes one product for optimal quality
batch_inputs = [
    {
        "batch": [split_product],
        "llm_parsed_results_file": llm_parsed_results_file
    }
    for split_product in split_products
]
```

## Key Outputs (Odoo Import Files)
- `attributes.csv` - Product attributes and values with External IDs
- `product_templates.csv` - Product templates with attribute line configurations
- `product_variants.csv` - Individual variants with SKU mappings
- `inventory_adjustments.csv` - Stock level adjustments

## Commands
- `uv run crewai run` - Run the complete pipeline
- `uv run train` - Train the AI agents
- `uv run replay` - Replay previous runs
- `uv run test` - Run tests

## Development Notes
- **Hybrid Intelligence**: Combines fast deterministic processing with AI reasoning
- **Token Efficient**: Only 15% of products use LLM processing
- **External ID Strategy**: Uses deterministic External IDs for simplified Odoo imports
- **CSV-Only Output**: No Odoo API dependency, generates import-ready files
- **Quality Gates**: Built-in validation and human approval checkpoints
- **Vendor Agnostic**: Adaptable to different CSV formats and naming conventions

## Tool Development Best Practices
- **Use `@tool` decorator** for creating custom tools (preferred over BaseTool class)
- **Keep tools lightweight and token-efficient**
- **Avoid sending large data through LLM context**
- **Return structured data (dict/JSON) for agent consumption**
- **Separate deterministic processing from AI reasoning**
- **Use standardized file paths from crew inputs**
- **Implement progressive saving for large datasets**
- **Handle async processing with proper error management**

### Example Tool Pattern:
```python
from crewai.tools import tool
import json
from pathlib import Path

@tool
def csv_processor_tool(input_csv_file: str, output_dir: str) -> dict:
    """Process vendor CSV and separate clear vs unclear products."""
    # Load and validate CSV
    df = pd.read_csv(input_csv_file)
    
    # Apply regex parsing
    clear_products, unclear_products = process_products(df)
    
    # Save results to standardized paths
    clear_file = Path(output_dir) / "csv" / "clear_products.json" 
    unclear_file = Path(output_dir) / "csv" / "unclear_products.json"
    
    clear_file.parent.mkdir(parents=True, exist_ok=True)
    unclear_file.parent.mkdir(parents=True, exist_ok=True)
    
    with open(clear_file, 'w') as f:
        json.dump(clear_products, f, indent=2)
    
    with open(unclear_file, 'w') as f:
        json.dump(unclear_products, f, indent=2)
    
    return {
        "status": "success",
        "clear_count": len(clear_products),
        "unclear_count": len(unclear_products),
        "completion_rate": f"{(len(clear_products) / (len(clear_products) + len(unclear_products))) * 100:.1f}%"
    }
```

### Concurrent Processing Pattern:
```python
# Use kickoff_for_each_async for large datasets
async def process_large_dataset(self, products: List[Dict]) -> List[Dict]:
    """Process products concurrently with quality control."""
    
    # Prepare individual inputs for each product
    batch_inputs = [
        {
            "batch": [product],
            "output_file": f"{self.output_dir}/llm/batch_{i}.json"
        }
        for i, product in enumerate(products)
    ]
    
    # Process concurrently
    results = await self.crew.kickoff_for_each_async(inputs=batch_inputs)
    
    # Merge results with progressive saving
    return self._merge_and_save_results(results)
```

## Agent Integration Pattern:
```python
# CrewAI async processing pattern for large datasets
async def run_async(self):
    """Run pipeline with concurrent LLM processing"""
    
    # Step 1: CSV processing (deterministic)
    csv_result = self.crew.kickoff(inputs={
        'input_csv_file': self.input_csv_file,
        'output_dir': self.output_dir
    })
    
    # Step 2: Concurrent LLM processing for unclear products
    batch_inputs = self._prepare_batch_inputs(unclear_products)
    results = await self.smart_parser_crew.kickoff_for_each_async(
        inputs=batch_inputs
    )
    
    # Step 3: Merge and continue pipeline
    return self._merge_results(csv_result, llm_results)
```

## Smart Parser Agent Task Configuration
```yaml
smart_parse_task:
  description: >
    You are an expert at extracting attributes from product text. You will receive a batch containing 
    multiple attribute texts in the {batch} input. Each item has an index and attributes_text to analyze.
    
    Your job: For each attributes_text, identify what attributes are present and extract their values.
    
    Common attributes you might find:
    - Flavors (e.g., "Cherry Lime", "Vanilla", "Apple Ice")
    - Nicotine strength in mg (e.g., "12mg", "6mg", "50mg")  
    - Volume in ml (e.g., "60mL", "100mL", "30ml")
    - Colors (e.g., "Black", "Blue", "Rainbow")
    - Technical specs (e.g., "0.2ohm", "80W", "1.0ohm")
    
    Rules:
    - Extract any attribute you can identify from the text
    - Clean up values (remove "(Discontinued)", convert "mg" to numbers)
    - If text seems like hardware specs or colors, those are valid attributes too
    - If text is empty or unclear, return empty attributes object
  expected_output: >
    Return ONLY a valid JSON array. Each object must have: index (number) and attributes (object with key-value pairs).
    Example: [{"index": 123, "attributes": {"flavor": "Cherry Lime", "nicotine_mg": 12, "volume_ml": 60}}]
    For hardware: [{"index": 456, "attributes": {"color": "Black", "resistance": "0.2ohm"}}]
  agent: smart_parser
```

## Human Checkpoints
The Orchestrator agent requests approval at key stages:
- **Data Quality Review**: Parsing results and error rates ("85.5% completion on 551 unclear products")
- **Attribute Taxonomy**: Standardized attribute values from LLM extraction
- **Category Mapping**: Category assignments using extracted brand information
- **Final Import Review**: Generated CSV files and import strategy

## Performance Metrics
- **Total Products**: 2,508 products in VWU_Product_List.csv
- **Regex Success**: ~2,000 products (85%) processed deterministically
- **LLM Processing**: 551 products (15%) requiring AI assistance
- **LLM Success Rate**: 85.5% completion (471/551 products parsed)
- **Brand Extraction**: Automatic brand identification for analytics
- **Processing Speed**: Concurrent batch processing with async architecture
- **Token Efficiency**: Only attributes_text sent to LLM (reduced context)
- **Quality Control**: Consistent product naming across product variants

## DEVELOPMENT STATUS

### ✅ COMPLETED COMPONENTS

#### 1. Orchestrator Agent (IMPLEMENTED)
**Role**: Project manager with decision-making intelligence  
**Implementation**: 
- Coordinates CSV processing and LLM parsing workflows
- Manages concurrent processing using `kickoff_for_each_async`
- Evaluates data quality and parsing completion rates
- Provides standardized file path management through crew inputs
- Handles workflow decisions and error management

#### 2. Smart Parser Agent (IMPLEMENTED)
**Role**: Product name intelligence specialist for complex cases
**Implementation**:
- Processes 551 unclear products that failed regex parsing
- Uses three-part parsing strategy for brand, product, and attribute extraction
- Implements natural attribute discovery without rigid schema constraints
- Achieves 85.5% completion rate with consistent product naming
- Uses concurrent processing for scalability

#### 3. Category Mapper Tool (IMPLEMENTED)
**Purpose**: Standardize product categories using existing Odoo categories
**Implementation**:
- Maps 3,725 products to existing Odoo categories (E-Juice, Kit, Coil, etc.)
- Uses intelligent keyword matching and brand-based fallback logic
- Results: 76% E-Juice, 15% Saleable fallback, 9% hardware categories
- Generates `category_mappings.json` and `category_stats.json`

#### 4. Attribute Builder Tool (IMPLEMENTED)
**Purpose**: Generate two separate attribute CSVs for existing vs new attributes
**Implementation**:
- Loads existing Odoo attributes from `odoo_attributes.csv`
- Uses external IDs for existing attributes to prevent duplicates
- Separates existing attribute values from new attribute creation
- **Outputs**:
  - `existing_attributes_values.csv`: 1,313 records (id,name,value/value format)
  - `new_attributes.csv`: 45 records (value/value,attribute,display_type,create_variant format)
- **Statistics**: 12 existing attributes reused, 15 new attributes created
- **Human-in-the-Loop**: Supports checkpoint system for attribute import approval

#### 5. Template Builder Tool (IMPLEMENTED)
**Purpose**: Create product template records with correct attribute-value mapping
**Implementation**:
- Groups variants by product_name (brand + name combination)
- Uses attribute-specific value mappings to prevent cross-contamination
- Calculates average pricing and attribute line configurations
- **Fixed Issue**: Resolved attribute-value mixup where nicotine values were assigned to flavor attributes
- **Output**: `new_templates.csv` with proper External ID references
- **Format**: Multiple rows per template (one for each attribute)
- **Statistics**: Generates templates for product lines with multiple attribute rows per template

#### 6. Advanced Processing Features
- **File Path Standardization**: All paths managed through crew inputs
- **Concurrent Processing**: `kickoff_for_each_async` implementation
- **Three-Part Parsing**: Brand + Product + Attributes extraction
- **Token Optimization**: Only attributes_text sent to LLM
- **Quality Assurance**: Progressive saving and error handling
- **Brand Analytics**: Automatic brand extraction for categorization
- **Skip Parsing Flag**: `SKIP_PARSING=True` for development efficiency
- **Attribute-Specific Value Mapping**: Prevents value ID cross-contamination between attributes

### 🚧 NEXT DEVELOPMENT TASKS (Priority Order)

#### 1. Build Variant Builder Tool (MEDIUM PRIORITY)
**Purpose**: Generate product variant records
**Implementation Needed**:
- Link variants to their parent templates
- Map SKUs and create variant-specific External IDs
- Handle attribute value combinations
- Output `product_variants.csv` for Odoo import

#### 2. Build Inventory Builder Tool (LOW PRIORITY)
**Purpose**: Create inventory adjustment records
**Implementation Needed**:
- Consolidate quantities by variant and location
- Generate stock level adjustments
- Output `inventory_adjustments.csv` for Odoo import

### 📊 CURRENT ACHIEVEMENTS
- ✅ 85% regex processing (fast deterministic)
- ✅ 15% AI processing (551 products, 85.5% completion rate)
- ✅ Brand extraction and analytics capability
- ✅ Consistent product naming across variants
- ✅ Token-efficient LLM processing
- ✅ Concurrent processing architecture
- ✅ Quality gates and error handling
- ✅ Standardized file path management
- ✅ Category mapping (3,725 products → 8 Odoo categories)
- ✅ Attribute separation (1,313 existing values + 45 new attributes)
- ✅ Template generation with correct attribute-value mapping
- ✅ External ID management for Odoo import compatibility
- ✅ Human-in-the-loop checkpoint system for attribute imports