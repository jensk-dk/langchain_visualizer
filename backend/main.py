from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Dict, Any, Optional, Literal
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

        # Create JSON spec for the tools
        json_spec = JsonSpec(
            dict_=merged_data,
            max_value_length=1000,  # Limit the length of displayed values
            num_examples=3  # Number of examples to show in array values
        )
        
        # Create the toolkit and agent
        toolkit = JsonToolkit(spec=json_spec)
        
        # Print available tools for debugging
        print("\nAvailable tools:")
        for tool in toolkit.get_tools():
            print(f"- {tool.name}: {tool.description}")
        
        agent_executor = create_json_agent(
            llm=llm,
            toolkit=toolkit,
            verbose=True
        ).with_config({
            "handle_parsing_errors": True,
            "max_iterations": 10
        })
        
        # Enhance the query to handle multiple files
        enhanced_query = f"""You are analyzing test report data. The data is stored in a JSON structure with test reports in the 'merged_data' array.

Each test report in the array has this structure:
- id: unique identifier
- title: test case title
- state: test result state (e.g., "Successful", "Failed")
- test_case_id: identifier for the test case
- created: timestamp when the test started
- last_changed: timestamp when the test finished
- timed_out: boolean indicating if the test timed out

Your task is to analyze this data and provide:
1. Total number of test cases (count of unique test_case_id values)
2. Success rate (percentage of tests with state "Successful")
3. Distribution of test states (count for each unique state value)
4. Average test duration in seconds (difference between last_changed and created timestamps)
5. Top 5 most frequently occurring test case IDs with their counts
6. Any patterns or anomalies in the data

Format the numeric results precisely, for example:
- Total test cases: 150
- Success rate: 85.7%
- Average duration: 45.2 seconds

To access the data, you can use these tools:
1. json_spec_list_keys: Lists all available keys in the JSON structure
2. json_spec_get_value: Gets the value at a specific path in the JSON structure

Example usage:
1. To see available keys:
   Action: json_spec_list_keys
   
2. To get the test reports array:
   Action: json_spec_get_value
   Action Input: "merged_data"

Start by listing the available keys to confirm the data structure."""
        
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
            
            return {
                "message": result["output"] if isinstance(result, dict) else str(result),
                "visualization": plot_json,
                "success": True,
                "files_processed": len(loaded_files),
                "total_files_found": len(json_files)
            }
        except Exception as e:
            return {
                "message": result["output"] if isinstance(result, dict) else str(result),
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