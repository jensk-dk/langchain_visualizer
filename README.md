# S3 JSON Visualizer

A web application that visualizes and analyzes JSON files stored in AWS S3 buckets using natural language queries.

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
- AWS credentials with S3 access
- OpenAI API key

## Configuration

### Environment Variables

Create a `.env` file in the `backend` directory with the following variables:

```env
# AWS Configuration
AWS_ACCESS_KEY_ID=your_aws_access_key
AWS_SECRET_ACCESS_KEY=your_aws_secret_key
AWS_DEFAULT_REGION=your_aws_region

# OpenAI Configuration
OPENAI_API_KEY=your_openai_api_key
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
pip install -r requirements.txt
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
python main.py
```

The backend will start on http://localhost:55317

### Start the Frontend

1. In a new terminal, navigate to the frontend directory:
```bash
cd s3_visualizer/frontend
```

2. Start the development server:
```bash
npm run dev
```

The frontend will start on http://localhost:53903

## Usage

1. Open your browser and navigate to http://localhost:53903
2. Enter your S3 bucket name
3. (Optional) Enter a prefix to filter JSON files
4. Set the maximum number of files to process (default: 100)
5. Click "List JSON Files" to see available JSON files
6. Enter your query about the data
7. Click "Analyze Data" to process and visualize the results

### Example Queries

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
   - Verify AWS credentials and permissions
   - Check OpenAI API key is valid
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

- The backend uses FastAPI for API endpoints
- LangChain is used for natural language processing
- Plotly is used for data visualization
- Vue.js 3 with Composition API for frontend
- Vite for frontend development and building
- Axios for API communication

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Submit a pull request

## License

MIT License - See LICENSE file for details