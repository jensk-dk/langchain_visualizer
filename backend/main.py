from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
import boto3
import json
from langchain.agents import create_json_agent
from langchain.agents.agent_toolkits import JsonToolkit
from langchain.tools.json.tool import JsonSpec
from langchain.llms import OpenAI
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
    bucket_name: str
    prefix: Optional[str] = ""  # Optional prefix to filter JSON files in the bucket
    max_files: Optional[int] = 100  # Maximum number of files to process

@app.get("/")
async def root():
    return {"message": "S3 JSON Visualizer API"}

def load_json_file(s3, bucket: str, key: str) -> Dict:
    """Load a single JSON file from S3."""
    try:
        response = s3.get_object(Bucket=bucket, Key=key)
        return json.loads(response['Body'].read().decode('utf-8'))
    except Exception as e:
        print(f"Error loading file {key}: {str(e)}")
        return None

def merge_json_data(json_files: List[Dict]) -> Dict:
    """Merge multiple JSON files into a single structure."""
    if not json_files:
        return {}
    
    # If the JSON files are arrays, concatenate them
    if all(isinstance(f, list) for f in json_files):
        return {"merged_data": [item for f in json_files for item in f]}
    
    # If the JSON files are objects, merge them with numbered keys
    merged = {"files": {}}
    for i, data in enumerate(json_files):
        merged["files"][f"file_{i}"] = data
    return merged

@app.get("/list_files")
async def list_json_files(bucket_name: str, prefix: str = ""):
    """List all JSON files in the specified S3 bucket and prefix."""
    try:
        s3 = boto3.client('s3')
        paginator = s3.get_paginator('list_objects_v2')
        
        json_files = []
        for page in paginator.paginate(Bucket=bucket_name, Prefix=prefix):
            if 'Contents' in page:
                for obj in page['Contents']:
                    if obj['Key'].lower().endswith('.json'):
                        json_files.append({
                            'key': obj['Key'],
                            'size': obj['Size'],
                            'last_modified': obj['LastModified'].isoformat()
                        })
        
        return {
            "files": json_files,
            "count": len(json_files)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/analyze")
async def analyze_data(request: QueryRequest):
    try:
        # Initialize S3 client
        s3 = boto3.client('s3')
        
        # List all JSON files in the bucket with the given prefix
        paginator = s3.get_paginator('list_objects_v2')
        json_files = []
        
        for page in paginator.paginate(Bucket=request.bucket_name, Prefix=request.prefix):
            if 'Contents' in page:
                for obj in page['Contents']:
                    if obj['Key'].lower().endswith('.json'):
                        json_files.append(obj['Key'])
                        if len(json_files) >= request.max_files:
                            break
                if len(json_files) >= request.max_files:
                    break
        
        if not json_files:
            raise HTTPException(status_code=404, detail="No JSON files found in the specified bucket and prefix")
        
        # Load JSON files in parallel
        with ThreadPoolExecutor(max_workers=min(10, len(json_files))) as executor:
            loaded_files = list(executor.map(
                lambda key: load_json_file(s3, request.bucket_name, key),
                json_files
            ))
        
        # Remove None values (failed loads)
        loaded_files = [f for f in loaded_files if f is not None]
        
        if not loaded_files:
            raise HTTPException(status_code=500, detail="Failed to load any JSON files")
        
        # Merge the JSON data
        merged_data = merge_json_data(loaded_files)
        
        # Create JSON agent with merged data
        json_spec = JsonSpec(dict_=merged_data)
        json_toolkit = JsonToolkit(spec=json_spec)
        
        # Initialize the agent with OpenAI
        agent = create_json_agent(
            llm=OpenAI(temperature=0),
            toolkit=json_toolkit,
            verbose=True
        )
        
        # Enhance the query to handle multiple files
        enhanced_query = f"""Analyze the following data from multiple JSON files:
{request.query}
Note that the data might be in 'merged_data' if the files were arrays, or in 'files.file_X' if they were objects.
Return the result in a format suitable for visualization."""
        
        # Execute the query
        result = agent.run(enhanced_query)
        
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
                # Create a basic visualization based on data types
                numeric_cols = df.select_dtypes(include=['int64', 'float64']).columns
                if len(numeric_cols) >= 2:
                    fig = px.scatter(df, x=numeric_cols[0], y=numeric_cols[1])
                elif len(numeric_cols) == 1:
                    fig = px.histogram(df, x=numeric_cols[0])
                else:
                    # Create a count plot of the first categorical column
                    first_col = df.columns[0]
                    value_counts = df[first_col].value_counts()
                    fig = go.Figure(data=[go.Bar(x=value_counts.index, y=value_counts.values)])
                
                plot_json = json.loads(plotly.utils.PlotlyJSONEncoder().encode(fig))
            else:
                plot_json = None
            
            return {
                "message": result,
                "visualization": plot_json,
                "success": True,
                "files_processed": len(loaded_files),
                "total_files_found": len(json_files)
            }
        except Exception as e:
            return {
                "message": result,
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
    uvicorn.run(app, host="0.0.0.0", port=55317)