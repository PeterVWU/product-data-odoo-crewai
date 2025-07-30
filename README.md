# Product Data Odoo - CrewAI Data Processing Pipeline

A CrewAI-powered data cleaning and transformation pipeline that converts vendor CSV files into Odoo-ready import files for e-liquid product data.

## Overview

This pipeline processes raw vendor product data and generates clean, structured CSV files for direct import into Odoo. The system uses a hybrid approach combining deterministic data processing tools with AI agents for complex parsing tasks.

## Architecture

### 🤖 AI Agents (LLM-Powered)

#### 1. Orchestrator Agent (Project Manager)
**Role**: Controls the entire pipeline workflow and decision-making

**Responsibilities**:
- Coordinates task execution and dependencies
- Validates data quality at each step
- Manages human approval checkpoints
- Makes routing decisions based on data characteristics
- Provides final summary and import instructions

**Intelligence**: 
- Evaluates data quality: "This batch has 15% parsing failures, should we proceed?"
- Workflow decisions: "Categories look inconsistent, routing to manual review"
- Final approval: "Ready to generate 2,508 product templates for Odoo import?"

#### 2. Smart Parser Agent (Product Name Intelligence)
**Role**: Handles complex product name parsing that requires reasoning

**Responsibilities**:
- Parses ambiguous product names using natural language understanding
- Handles edge cases and non-standard naming patterns
- Adapts to new vendor formats and product types
- Processes products that fail regex pattern matching

**Intelligence**:
- Complex parsing: "7DZE - 7Daze Click-Mates Pods (20mg 18mL; 9mL x2) - Cherry Lime"
  - Extracts: Brand="7DZE", Product="7DZE - 7Daze Click-Mates Pods", Flavor="Cherry Lime", Nicotine=20mg
- Hardware detection: "FRMX - Freemax Coils - SS316 X1 Mesh 0.12ohm" 
  - Recognizes: Brand="FRMX", Product="FRMX - Freemax Coils", Resistance="0.12ohm"
- Processing: Uses CrewAI's `kickoff_for_each_async` for concurrent batch processing
- Quality: 85.5% completion rate with consistent product naming across variants

### 🔧 Processing Tools (Deterministic)

#### CSV Processor Tool
- **Function**: Data validation and column standardization
- **Input**: Raw vendor CSV files
- **Processing**: Column mapping, type validation, duplicate detection
- **Output**: Cleaned CSV with standard columns (sku, name, qty, price, category)

#### Category Mapper Tool  
- **Function**: Standardizes product categories using existing Odoo categories
- **Processing**: Intelligent keyword matching, brand-based fallback logic
- **Results**: 3,725 products mapped to 8 categories (76% E-Juice, 15% Saleable, 9% hardware)
- **Output**: `category_mappings.json` and `category_stats.json`

#### Attribute Builder Tool
- **Function**: Generates two separate attribute CSVs for existing vs new attributes
- **Processing**: Loads existing Odoo attributes, uses external IDs to prevent duplicates
- **Results**: 1,313 existing attribute values + 45 new attribute records
- **Output**: 
  - `existing_attributes_values.csv`: Add new values to existing attributes (id,name,value/value)
  - `new_attributes.csv`: Create new attributes (value/value,attribute,display_type,create_variant)

#### Template Builder Tool
- **Function**: Creates product template records with proper attribute-value mapping
- **Processing**: Groups variants by product line, uses attribute-specific value lookups
- **Features**: 
  - Limits to 2 attributes per template to prevent variant explosion
  - Priority system: flavor > nicotine_mg > resistance_ohm > coil_type > color
  - SKU support for simple products without attributes
  - Handles both variant templates and simple products
- **Output**: `new_templates.csv` with correct External ID references and SKU management

#### Variant Builder Tool (✅ COMPLETED)
- **Function**: Generates product variant import CSV using existing variant IDs from Odoo exports
- **Processing**: 
  - Uses stored-attribute-driven matching for maximum compatibility
  - Handles simple products (no attributes) and complex multi-attribute variants
  - Maps products to existing Odoo variants using flexible attribute matching
  - Supports partial attribute matching for evolved templates
- **Performance**: **95.8% success rate** (3,209 out of 3,350 products matched)
- **Output**: `product_variant_import.csv` with format: `id,name,product_template_variant_value_ids/id,default_code,standard_price`

#### Inventory Builder Tool
- **Function**: Creates inventory adjustment records
- **Processing**: Consolidates quantities by variant and location
- **Output**: `inventory_adjustments.csv` for stock levels

## Data Flow

```
Vendor CSV → CSV Processor Tool → Smart Parser Agent → 
Category Mapper Tool → Attribute Builder Tool → 
Template Builder Tool → Variant Builder Tool → 
Inventory Builder Tool → Orchestrator Approval → 
Ready-to-Import Odoo CSV Files
```

## Pipeline Stages

### 1. Data Ingestion & Validation
- Load vendor CSV files with configurable encoding
- Map vendor columns to standard schema (sku, name, qty, price, category)
- Validate data types and detect quality issues
- Generate data quality report

### 2. Product Name Parsing (Hybrid Approach)
- **Regex Processing**: Handle 85% of products with standard patterns
  - Pattern: `[PRODUCT_NAME] - [FLAVOR] [NICOTINE]mg`
  - Example: "7DZE - 7Daze Fusion TFN - Banana Cantaloupe 03mg"
- **AI Processing**: Handle 15% complex cases requiring reasoning
  - Three-part parsing: `[BRAND] - [PRODUCT_NAME] - [ATTRIBUTES]`
  - Concurrent processing using `kickoff_for_each_async`
  - Smart attribute extraction from text fragments
  - Example: "7DZE - 7Daze (LIQ FB)(60mL) Reds - Fruit Mix Iced 12mg"
    - Brand: "7DZE"
    - Product: "7DZE - 7Daze (LIQ FB)(60mL) Reds"
    - Attributes: "Fruit Mix Iced 12mg" → {flavor: "Fruit Mix Iced", nicotine_mg: 12}

### 3. Product Structure Generation
- **Templates**: Group products by base product line (brand + volume)
  - Example: "7DZE - 7Daze (LIQ FB)(100mL) Fusion TFN" → 42 variants
- **Variants**: Individual products with flavor and nicotine combinations
- **Attributes**: Extract unique values (flavors, nicotine strengths, volumes)

### 4. Category & Attribute Normalization
- Standardize category hierarchies for Odoo compatibility
- Deduplicate and normalize attribute values
- Generate External IDs for all entities

### 5. Odoo Import File Generation
Generate four main CSV files for Odoo import:

#### `attributes.csv`
Product attributes and their possible values (1,355 records)
```
value,attribute,attribute/id,display_type,create_variant
# Examples:
.357(Buckshot),,__export__.product_attribute_38_d222431b,,    # New value for existing attribute
Jet Black,Shade,,radio,instantly                              # New attribute
```

#### `product_templates.csv` 
Product templates with attribute line configurations
```
template_ext_id, name, category_ext_id, type, sale_ok, list_price, 
attribute_line_1_attr_ext_id, attribute_line_1_value_ext_ids
```

#### `product_variants.csv`
Individual product variants with SKU mappings
```
variant_ext_id, template_ext_id, attribute_value_ext_ids, 
internal_reference, barcode
```

#### `inventory_adjustments.csv`
Stock level adjustments for inventory management
```
variant_ext_id, location_ext_id, quantity
```

## Key Features

- **Hybrid Intelligence**: Fast regex processing (85%) + AI for complex cases (15%)
- **Token Efficient**: Only 467/3,817 products use LLM processing
- **External ID Strategy**: Uses existing Odoo external IDs to prevent duplicates
- **Quality Gates**: Built-in validation and human approval checkpoints
- **Existing Data Integration**: Loads and reuses existing Odoo categories and attributes
- **Vendor Agnostic**: Adaptable to different CSV formats and naming conventions
- **Offline Processing**: No Odoo API dependency, pure CSV generation
- **Skip Parsing Mode**: Development flag to skip expensive LLM processing
- **Advanced Variant Matching**: Stored-attribute-driven matching achieving 95.8% success rate
- **Template Evolution Support**: Handles templates where attributes were added/removed over time
- **Single-Value Attribute Handling**: Correctly processes templates with non-variant attributes

## Usage

```bash
# Run the complete pipeline
uv run crewai run

# Train the AI agents
uv run train

# Replay previous runs
uv run replay

# Run tests
uv run test
```

## Implementation Status

### ✅ Completed Components
- **Orchestrator Agent**: Fully implemented with workflow coordination
- **Smart Parser Agent**: Implemented with three-part parsing and LLM integration
- **CSV Processor Tool**: Working with standardized file paths
- **Product Parser Tool**: Hybrid regex + AI approach operational
- **Category Mapper Tool**: Maps 3,817 products to existing Odoo categories
- **Attribute Builder Tool**: Generates attribute CSVs with existing/new attribute separation
- **Template Builder Tool**: Creates product templates with attribute-value mapping, variant limiting, and SKU support
- **Variant Builder Tool**: **COMPLETED** with stored-attribute-driven matching achieving 95.8% success rate
- **Concurrent Processing**: `kickoff_for_each_async` implementation for scaling
- **File Path Management**: Standardized paths passed through crew inputs
- **Quality Assurance**: 85.5% completion rate on 551 complex products
- **External ID Management**: Prevents duplicates in Odoo imports
- **Human-in-the-Loop**: Checkpoint system for attribute import approval
- **Advanced Variant Matching**: Handles simple products, single-value attributes, and template evolution

### 🚧 Pending Components
- **Inventory Builder Tool**: For inventory adjustment records (low priority)

## Output

The pipeline generates a complete set of CSV files ready for sequential import into Odoo:

1. Import `attributes.csv` to create product attributes
2. Import `product_templates.csv` to create base products
3. Import `product_variants.csv` to create variant configurations
4. Import `inventory_adjustments.csv` to set stock levels

## Human Checkpoints

The Orchestrator agent will request approval at key stages:

- **Data Quality Review**: Approve parsing results and error rates
- **Attribute Taxonomy**: Review and approve standardized attribute values
- **Category Mapping**: Confirm category assignments and hierarchy
- **Final Import Review**: Approve generated CSV files and import strategy

This ensures data quality while maintaining efficient automated processing.