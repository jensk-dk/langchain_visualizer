# JSON Data Visualizer

A web application that visualizes and analyzes JSON files using natural language queries. Supports both local files and AWS S3 buckets as data sources.

## Project Structure

```
s3_visualizer/
├── frontend/          # Vue.js frontend application
│   ├── src/
│   │   ├── App.vue   # Main application component
│   │   └── main.js   # Application entry point
│   ├── index.html    # HTML template
│   ├── package.json  # Frontend dependencies
│   └── vite.config.js# Vite configuration
├── backend/          # FastAPI backend application
│   ├── main.py      # Main API server
│   └── requirements.txt # Python dependencies
└── README.md        # This file
```

## Prerequisites

- Python 3.8 or higher
- Node.js 16 or higher
- npm 7 or higher
- Anthropic API key (for Claude)
- (Optional) AWS credentials with S3 access

## Configuration

### Environment Variables

Create a `.env` file in the `backend` directory with the following variables:

```env
# Required: Anthropic Configuration
ANTHROPIC_API_KEY=your_anthropic_api_key

# Optional: AWS Configuration (only needed for S3 access)
AWS_ACCESS_KEY_ID=your_aws_access_key
AWS_SECRET_ACCESS_KEY=your_aws_secret_key
AWS_DEFAULT_REGION=your_aws_region
```

## Installation

### Backend Setup

1. Navigate to the backend directory:
```bash
cd s3_visualizer/backend
```

2. Create and activate a virtual environment (optional but recommended):
```bash
python -m venv venv
source venv/bin/activate  # On Windows, use: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install langchain langchain-community langchain-anthropic openai plotly pandas fastapi uvicorn
```

### Frontend Setup

1. Navigate to the frontend directory:
```bash
cd s3_visualizer/frontend
```

2. Install dependencies:
```bash
npm install
```

## Running the Application

### Start the Backend

1. Make sure you're in the backend directory:
```bash
cd s3_visualizer/backend
```

2. Start the FastAPI server:
```bash
ANTHROPIC_API_KEY=your_api_key uvicorn main:app --host 0.0.0.0 --port 53840 --reload
```

The backend will start on http://localhost:53840

### Start the Frontend

1. In a new terminal, navigate to the frontend directory:
```bash
cd s3_visualizer/frontend
```

2. Start the development server:
```bash
npm run dev -- --port 59573 --host 0.0.0.0
```

The frontend will start on http://localhost:59573

## Usage

1. Open your browser and navigate to http://localhost:59573
2. Choose your data source:
   - Local: Uses JSON files from the `json_files` directory in the project root
   - S3: Uses JSON files from an AWS S3 bucket
3. For S3:
   - Enter your bucket name
   - (Optional) Enter a prefix to filter JSON files
4. Set the maximum number of files to process (default: 100)
5. Click "List JSON Files" to see available files
6. Enter your query about the data
7. Click "Analyze Data" to process and visualize the results

### Example Queries

For test reports:
- "What is the success rate and distribution of test states?"
- "Show me the most common test cases"
- "How long do tests typically take to run?"
- "What is the failure rate and which tests fail most often?"

For general JSON data:
- "Show me the distribution of values in field X"
- "What are the top 5 most common values in field Y?"
- "Is there any correlation between field A and field B?"
- "Compare the structure of different files and highlight any inconsistencies"

## Building for Production

### Frontend Build

```bash
cd s3_visualizer/frontend
npm run build
```

The built files will be in the `dist` directory.

### Backend Production Setup

For production deployment, consider:
- Using a production WSGI server like uvicorn or gunicorn
- Setting up proper SSL/TLS
- Implementing authentication
- Configuring proper CORS settings
- Setting up monitoring and logging

Example production backend start:
```bash
uvicorn main:app --host 0.0.0.0 --port 55317 --workers 4
```

## Security Considerations

1. AWS Security:
   - Use IAM roles with minimal required permissions
   - Consider using AWS Secrets Manager for credentials
   - Enable S3 bucket encryption

2. API Security:
   - Implement authentication for production
   - Use HTTPS in production
   - Set proper CORS policies
   - Rate limit API endpoints

3. Data Security:
   - Validate and sanitize user inputs
   - Handle sensitive data appropriately
   - Implement proper error handling

## Troubleshooting

1. Backend Issues:
   - Check environment variables are set correctly
   - Verify Anthropic API key is valid
   - For S3: Verify AWS credentials and permissions
   - Look for error messages in the backend logs

2. Frontend Issues:
   - Check browser console for errors
   - Verify API endpoint URLs are correct
   - Clear browser cache if needed
   - Check network tab for API responses

3. S3 Access Issues:
   - Verify bucket permissions
   - Check AWS credentials
   - Confirm bucket region matches configuration

## Development Notes

- Backend:
  - FastAPI for API endpoints
  - LangChain with Claude (Anthropic) for natural language processing
  - Plotly for data visualization
  - Support for both local files and S3 data sources
- Frontend:
  - Vue.js 3 with Composition API
  - Vite for development and building
  - Dark mode support
  - Responsive design
  - Axios for API communication

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Submit a pull request

## License

MIT License - See LICENSE file for details