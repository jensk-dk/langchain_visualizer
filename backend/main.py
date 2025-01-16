from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Dict, Any, Optional, Literal, Union
import boto3
import json
import os
from pathlib import Path
from langchain.agents import AgentExecutor, create_json_agent
from langchain_community.tools.json.tool import JsonGetValueTool, JsonListKeysTool, JsonSpec
from langchain_community.agent_toolkits.json.toolkit import JsonToolkit
from langchain_anthropic import ChatAnthropic
import plotly.express as px
import plotly.utils
import plotly.graph_objects as go
import pandas as pd
from concurrent.futures import ThreadPoolExecutor
from io import StringIO

app = FastAPI()

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class QueryRequest(BaseModel):
    query: str
    source_type: Literal["local", "s3"] = "local"  # Default to local directory
    bucket_name: Optional[str] = None  # Required for S3 mode
    prefix: Optional[str] = ""  # Optional prefix for S3 or subdirectory for local mode
    max_files: Optional[int] = 100  # Maximum number of files to process
    dark_mode: Optional[bool] = False  # Dark mode setting for visualizations

@app.get("/")
async def root():
    return {"message": "JSON Visualizer API"}

def load_json_file_s3(s3, bucket: str, key: str) -> Dict:
    """Load a single JSON file from S3."""
    try:
        response = s3.get_object(Bucket=bucket, Key=key)
        return json.loads(response['Body'].read().decode('utf-8'))
    except Exception as e:
        print(f"Error loading S3 file {key}: {str(e)}")
        return None

def load_json_file_local(file_path: str) -> Dict:
    """Load a single JSON file from local directory."""
    try:
        with open(file_path, 'r') as f:
            content = f.read()
            # Check if the content starts with { and ends with },
            # which indicates multiple JSON objects
            if content.strip().startswith('{') and content.strip().endswith('}'):
                # Split by "},\n{" to separate objects, then add brackets back
                objects = [obj + '}' if not obj.endswith('}') else obj 
                         for obj in content.strip().rstrip(',').split('},\n{')]
                objects[0] = objects[0].lstrip('{')  # Remove leading { from first object
                objects[-1] = objects[-1].rstrip('}')  # Remove trailing } from last object
                # Reconstruct as a proper JSON array
                array_content = '[{' + '},{'.join(objects) + '}]'
                return json.loads(array_content)
            else:
                # Regular JSON file
                return json.loads(content)
    except Exception as e:
        print(f"Error loading local file {file_path}: {str(e)}")
        print("Content preview:")
        try:
            with open(file_path, 'r') as f:
                print(f.read()[:500] + "...")
        except Exception as read_error:
            print(f"Could not read file for preview: {read_error}")
        return None

def _format_data(data: Union[List, Dict]) -> List[str]:
    """Format JSON data into readable lines."""
    lines = []
    if isinstance(data, list):
        for item in data:
            if isinstance(item, dict):
                for key, value in item.items():
                    lines.append(f"{key}: {value}")
            else:
                lines.append(str(item))
    elif isinstance(data, dict):
        for key, value in data.items():
            lines.append(f"{key}: {value}")
    return lines

def merge_json_data(json_files: List[Dict]) -> Dict:
    """Merge multiple JSON files into a single structure."""
    if not json_files:
        return {"merged_data": []}
    
    # Convert single objects to lists for consistent handling
    all_reports = []
    for f in json_files:
        if isinstance(f, dict):
            # Single test report
            all_reports.append(f)
        elif isinstance(f, list):
            # List of test reports
            all_reports.extend(f)
        else:
            print(f"Warning: Unexpected data type in JSON file: {type(f)}")
            continue
    
    print(f"\nProcessed {len(all_reports)} test reports")
    
    # Validate the structure of each report
    valid_reports = []
    for report in all_reports:
        if isinstance(report, dict) and all(key in report for key in ['id', 'state', 'test_case_id']):
            valid_reports.append(report)
        else:
            print(f"Warning: Invalid report structure: {report}")
    
    print(f"Found {len(valid_reports)} valid test reports")
    
    return {
        "merged_data": valid_reports,
        "metadata": {
            "total_reports": len(valid_reports),
            "data_structure": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": ["id", "state", "test_case_id", "created", "last_changed"]
                }
            }
        }
    }

def get_local_json_files(prefix: str = "") -> List[Dict]:
    """List all JSON files in the local json_files directory."""
    json_files = []
    # Get the backend directory path
    backend_dir = Path(__file__).parent
    # json_files directory is one level up from backend
    base_dir = backend_dir.parent / "json_files"
    search_dir = base_dir / prefix if prefix else base_dir
    
    print(f"Searching for JSON files in: {search_dir}")
    
    try:
        # Ensure the directory exists
        if not search_dir.exists():
            print(f"Directory does not exist: {search_dir}")
            return []
            
        # List all files to debug
        print("All files in directory:")
        for f in search_dir.iterdir():
            print(f"  {f}")
            
        for file_path in search_dir.rglob("*.json"):
            print(f"Found JSON file: {file_path}")
            stats = file_path.stat()
            rel_path = str(file_path.relative_to(base_dir))
            json_files.append({
                'key': rel_path,
                'size': stats.st_size,
                'last_modified': stats.st_mtime_ns
            })
            
        print(f"Total JSON files found: {len(json_files)}")
    except Exception as e:
        print(f"Error listing local files: {str(e)}")
        import traceback
        traceback.print_exc()
    
    return json_files

def get_s3_json_files(bucket_name: str, prefix: str = "") -> List[Dict]:
    """List all JSON files in the specified S3 bucket and prefix."""
    json_files = []
    s3 = boto3.client('s3')
    paginator = s3.get_paginator('list_objects_v2')
    
    try:
        for page in paginator.paginate(Bucket=bucket_name, Prefix=prefix):
            if 'Contents' in page:
                for obj in page['Contents']:
                    if obj['Key'].lower().endswith('.json'):
                        json_files.append({
                            'key': obj['Key'],
                            'size': obj['Size'],
                            'last_modified': obj['LastModified'].isoformat()
                        })
    except Exception as e:
        print(f"Error listing S3 files: {str(e)}")
    
    return json_files

@app.get("/list_files")
async def list_json_files(source_type: str = "local", bucket_name: Optional[str] = None, prefix: str = ""):
    """List all JSON files from either local directory or S3 bucket."""
    try:
        if source_type == "local":
            json_files = get_local_json_files(prefix)
        elif source_type == "s3":
            if not bucket_name:
                raise HTTPException(status_code=400, detail="bucket_name is required for S3 source type")
            json_files = get_s3_json_files(bucket_name, prefix)
        else:
            raise HTTPException(status_code=400, detail="Invalid source_type. Must be 'local' or 's3'")
        
        return {
            "files": json_files,
            "count": len(json_files)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/analyze")
async def analyze_data(request: QueryRequest):
    try:
        print(f"Analyze request received: {request}")
        # Get list of JSON files based on source type
        if request.source_type == "local":
            json_files = get_local_json_files(request.prefix)
            json_files = [f['key'] for f in json_files][:request.max_files]
            
            if not json_files:
                raise HTTPException(status_code=404, detail="No JSON files found in the local directory")
            
            # Load JSON files in parallel
            backend_dir = Path(__file__).parent
            base_dir = backend_dir.parent / "json_files"
            with ThreadPoolExecutor(max_workers=min(10, len(json_files))) as executor:
                loaded_files = list(executor.map(
                    lambda key: load_json_file_local(str(base_dir / key)),
                    json_files
                ))
        
        elif request.source_type == "s3":
            if not request.bucket_name:
                raise HTTPException(status_code=400, detail="bucket_name is required for S3 source type")
            
            # Initialize S3 client
            s3 = boto3.client('s3')
            json_files = get_s3_json_files(request.bucket_name, request.prefix)
            json_files = [f['key'] for f in json_files][:request.max_files]
            
            if not json_files:
                raise HTTPException(status_code=404, detail="No JSON files found in the specified bucket and prefix")
            
            # Load JSON files in parallel
            with ThreadPoolExecutor(max_workers=min(10, len(json_files))) as executor:
                loaded_files = list(executor.map(
                    lambda key: load_json_file_s3(s3, request.bucket_name, key),
                    json_files
                ))
        
        else:
            raise HTTPException(status_code=400, detail="Invalid source_type. Must be 'local' or 's3'")
        
        # Remove None values (failed loads)
        loaded_files = [f for f in loaded_files if f is not None]
        
        if not loaded_files:
            raise HTTPException(status_code=500, detail="Failed to load any JSON files")
        
        # Merge the JSON data
        merged_data = merge_json_data(loaded_files)
        
        # Print the merged data structure for debugging
        print("\nMerged data structure contains these top-level keys:")
        print(list(merged_data.keys()))

        # Initialize the LLM
        llm = ChatAnthropic(
            model="claude-3-sonnet-20240229",
            temperature=0,
            api_key=os.getenv("ANTHROPIC_API_KEY"),
            max_tokens_to_sample=4000  # Set a maximum token limit
        )

        # Print the merged data structure for debugging
        print("\nMerged data structure:")
        print(json.dumps(merged_data, indent=2)[:500] + "...")

        # Create JSON spec for the tools
        # Ensure merged_data is properly structured
        if 'merged_data' not in merged_data:
            # If merged_data is not a key, it's probably the array itself
            data_dict = {
                "merged_data": merged_data.get("merged_data", merged_data)
            }
        else:
            data_dict = merged_data

        print("\nData being passed to JsonSpec:")
        print(json.dumps(data_dict, indent=2)[:500] + "...")
        
        json_spec = JsonSpec(
            dict_=data_dict,  # Use the properly structured data
            max_value_length=10000,  # Large limit for value length
            num_examples=100  # Large number of examples
        )
        
        # Create the toolkit and agent
        toolkit = JsonToolkit(spec=json_spec)
        
        # Print available tools and data structure for debugging
        print("\nAvailable tools:")
        for tool in toolkit.get_tools():
            print(f"- {tool.name}: {tool.description}")
            
        print("\nData structure:")
        print("- Root keys:", list(json_spec.dict_.keys()))
        print("- Merged data type:", type(merged_data))
        if isinstance(merged_data, dict):
            print("- Merged data keys:", list(merged_data.keys()))
        
        # Create the agent with more iterations and longer timeout
        agent_executor = create_json_agent(
            llm=llm,
            toolkit=toolkit,
            verbose=True,
            handle_parsing_errors=True,
            max_iterations=15,
            early_stopping_method="force",
            max_execution_time=30.0  # 30 seconds timeout
        )
        
        # System instructions for the agent
        system_instructions = """You are analyzing test report data stored in a JSON structure. Follow these EXACT steps:

1. First, get the test reports:
   Action: json_spec_get_value
   Action Input: "merged_data"

2. After getting the data, analyze it to find:
   - Total number of reports
   - Unique test_case_id values
   - Count of reports in each state

3. Then provide your analysis in this EXACT format:

Final Answer:
Test Report Analysis:

Total Reports: [number]
Unique Test Cases: [number]

Test States:
- [State]: [count] ([percentage]%)
- [State]: [count] ([percentage]%)
...

IMPORTANT:
- If you can't get the data, respond with EXACTLY:
  Final Answer: Unable to access test report data.
- If you get the data but can't analyze it, respond with EXACTLY:
  Final Answer: Retrieved data but unable to analyze test reports.
- DO NOT show any code or calculations
- DO NOT include any explanations
- DO NOT use backticks (`) or code blocks
- DO NOT include any other text or formatting

Remember: Just get the data with ONE call to json_spec_get_value, analyze it, and show the results in the exact format shown above."""

        # Combine system instructions with user query
        enhanced_query = f"{system_instructions}\n\nUser query: {request.query}"
        
        # Execute the query
        result = agent_executor.invoke({"input": enhanced_query})
        
        # Attempt to create visualization
        try:
            # Convert merged data to DataFrame
            if "merged_data" in merged_data:
                df = pd.DataFrame(merged_data["merged_data"])
            else:
                # Combine data from multiple files
                dfs = []
                for file_data in merged_data["files"].values():
                    try:
                        if isinstance(file_data, list):
                            dfs.append(pd.DataFrame(file_data))
                        elif isinstance(file_data, dict):
                            dfs.append(pd.DataFrame([file_data]))
                    except Exception:
                        continue
                df = pd.concat(dfs, ignore_index=True) if dfs else None
            
            if df is not None:
                # Create visualizations specific to test reports
                figs = []
                
                # 1. Test States Distribution
                if 'state' in df.columns:
                    state_counts = df['state'].value_counts()
                    fig1 = go.Figure(data=[
                        go.Bar(
                            x=state_counts.index,
                            y=state_counts.values,
                            text=state_counts.values,
                            textposition='auto',
                        )
                    ])
                    fig1.update_layout(
                        title='Distribution of Test States',
                        xaxis_title='State',
                        yaxis_title='Count',
                        showlegend=False
                    )
                    figs.append(fig1)
                
                # 2. Test Duration Distribution
                if 'created' in df.columns and 'last_changed' in df.columns:
                    df['duration'] = pd.to_datetime(df['last_changed']) - pd.to_datetime(df['created'])
                    df['duration_seconds'] = df['duration'].dt.total_seconds()
                    fig2 = go.Figure(data=[
                        go.Histogram(
                            x=df['duration_seconds'],
                            nbinsx=30,
                            name='Duration'
                        )
                    ])
                    fig2.update_layout(
                        title='Distribution of Test Durations',
                        xaxis_title='Duration (seconds)',
                        yaxis_title='Count',
                        showlegend=False
                    )
                    figs.append(fig2)
                
                # 3. Top Test Cases
                if 'test_case_id' in df.columns:
                    test_case_counts = df['test_case_id'].value_counts().head(10)
                    fig3 = go.Figure(data=[
                        go.Bar(
                            x=test_case_counts.values,
                            y=test_case_counts.index,
                            orientation='h',
                            text=test_case_counts.values,
                            textposition='auto',
                        )
                    ])
                    fig3.update_layout(
                        title='Top 10 Most Frequent Test Cases',
                        xaxis_title='Count',
                        yaxis_title='Test Case ID',
                        height=400,
                        margin=dict(l=200),  # Add left margin for long test case IDs
                        showlegend=False
                    )
                    figs.append(fig3)
                
                # Combine all figures into a single plot with subplots
                if figs:
                    subplot_titles = [fig.layout.title.text for fig in figs]
                    fig = go.Figure()
                    for i, subfig in enumerate(figs):
                        for trace in subfig.data:
                            trace.update(visible=i==0)  # Only first plot visible initially
                            fig.add_trace(trace)
                    
                    # Add dropdown menu to switch between plots
                    # Set theme colors based on dark mode
                    bg_color = '#1a1a1a' if request.dark_mode else '#ffffff'
                    text_color = '#e0e0e0' if request.dark_mode else '#333333'
                    grid_color = '#444444' if request.dark_mode else '#dddddd'
                    
                    fig.update_layout(
                        updatemenus=[{
                            'buttons': [
                                {'label': title,
                                 'method': 'update',
                                 'args': [{'visible': [j==i for j in range(len(fig.data))]},
                                        {'title': title}]}
                                for i, title in enumerate(subplot_titles)
                            ],
                            'direction': 'down',
                            'showactive': True,
                            'x': 0.1,
                            'y': 1.15,
                            'bgcolor': bg_color,
                            'font': {'color': text_color}
                        }],
                        height=500,
                        title=subplot_titles[0],
                        paper_bgcolor=bg_color,
                        plot_bgcolor=bg_color,
                        font={'color': text_color},
                        xaxis={'gridcolor': grid_color, 'linecolor': grid_color},
                        yaxis={'gridcolor': grid_color, 'linecolor': grid_color}
                    )
                    plot_json = json.loads(plotly.utils.PlotlyJSONEncoder().encode(fig))
                else:
                    plot_json = None
            else:
                plot_json = None
            
            # Process the agent's response
            output = result["output"] if isinstance(result, dict) else str(result)
            print("\nRaw output from LLM:")
            print(output)
            
            # Extract content after "Final Answer:"
            if "Final Answer:" in output:
                output = output.split("Final Answer:")[1].strip()
            
            # Split into lines and process
            lines = output.split('\n')
            final_output = []
            print("\nProcessing lines...")
            
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                
                # Skip agent's internal dialogue
                if any(line.startswith(prefix) for prefix in [
                    "Thought:", "Action:", "Observation:", "Tool:", "System:", 
                    "Assistant:", "Human:"
                ]):
                    continue
                
                # Skip lines with template variables
                if "{" in line or "}" in line:
                    continue
                
                # Skip planning and explanation lines
                if any(line.startswith(prefix) for prefix in [
                    "I will", "Let me", "First", "Then", "Next", "Finally",
                    "To get", "To find", "To calculate", "Here's", "Here are",
                    "The most common", "This shows", "This indicates", "Based on"
                ]):
                    continue
                
                # Keep section headers
                if line.endswith(":") and not line.startswith("-"):
                    final_output.append("")  # Add blank line before section
                    final_output.append(line)
                    print(f"Added section header: {line}")
                    continue

                # Include lines that look like results
                if (line.startswith("-") or  # Bullet points
                    line.startswith("•") or  # Alternative bullet points
                    line.startswith("*") or  # Alternative bullet points
                    any(line.startswith(str(i) + ".") for i in range(1, 10)) or  # Numbered lists
                    ":" in line or  # Key-value pairs
                    "%" in line or  # Percentages
                    any(word in line.lower() for word in [
                        "total", "rate", "average", "distribution", 
                        "frequency", "count", "number", "success",
                        "failed", "passed", "overall"
                    ])):  # Statistics and results
                    final_output.append(line)
                    print(f"Added result line: {line}")
                else:
                    print(f"Skipped line: {line}")
                
            print("\nBefore cleaning, collected lines:")
            for line in final_output:
                print(f"  {line}")

            # Clean up the output
            cleaned_output = []
            prev_line = ""
            
            for line in final_output:
                # Skip duplicate lines
                if line == prev_line:
                    print(f"Skipping duplicate: {line}")
                    continue
                # Don't add blank line if previous line was blank
                if line == "" and prev_line == "":
                    print(f"Skipping extra blank line")
                    continue
                cleaned_output.append(line)
                prev_line = line
            
            # Remove leading/trailing blank lines
            while cleaned_output and cleaned_output[0] == "":
                cleaned_output.pop(0)
            while cleaned_output and cleaned_output[-1] == "":
                cleaned_output.pop()
            
            print("\nAfter cleaning, final lines:")
            for line in cleaned_output:
                print(f"  {line}")
            
            # Join the lines back together
            final_message = "\n".join(cleaned_output) if cleaned_output else "No analysis results available."
            
            return {
                "message": final_message,
                "visualization": plot_json,
                "success": True,
                "files_processed": len(loaded_files),
                "total_files_found": len(json_files)
            }
        except Exception as e:
            return {
                "message": final_message,
                "visualization": None,
                "success": True,
                "files_processed": len(loaded_files),
                "total_files_found": len(json_files),
                "visualization_error": str(e)
            }
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=53838)