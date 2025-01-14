<template>
  <div id="app">
    <h1>S3 JSON Visualizer</h1>
    
    <div class="input-container">
      <div class="input-group">
        <label>S3 Bucket Name:</label>
        <input v-model="bucketName" placeholder="Enter bucket name">
      </div>
      
      <div class="input-group">
        <label>Prefix (Optional):</label>
        <input v-model="prefix" placeholder="Enter prefix to filter JSON files">
      </div>
      
      <div class="input-group">
        <label>Max Files to Process:</label>
        <input type="number" v-model.number="maxFiles" min="1" max="1000" placeholder="Maximum number of files to process">
      </div>
      
      <button @click="listFiles" :disabled="loading || !bucketName">
        List JSON Files
      </button>
      
      <div v-if="filesList.length > 0" class="files-list">
        <h3>Available JSON Files ({{ filesList.length }}):</h3>
        <ul>
          <li v-for="file in filesList" :key="file.key">
            {{ file.key }} ({{ formatSize(file.size) }})
          </li>
        </ul>
      </div>
      
      <div class="input-group">
        <label>Query:</label>
        <textarea 
          v-model="query" 
          placeholder="Enter your query about the data"
          rows="3"
        ></textarea>
      </div>
      
      <button @click="analyzeData" :disabled="loading || !bucketName || !query">
        {{ loading ? 'Analyzing...' : 'Analyze Data' }}
      </button>
    </div>

    <div v-if="error" class="error">
      {{ error }}
    </div>

    <div v-if="result" class="result">
      <h3>Analysis Result:</h3>
      <p>{{ result.message }}</p>
      <p class="stats">
        Files processed: {{ result.files_processed }} / {{ result.total_files_found }}
      </p>
      
      <div v-if="result.visualization" ref="plotDiv" class="visualization"></div>
      <div v-if="result.visualization_error" class="error">
        Visualization error: {{ result.visualization_error }}
      </div>
    </div>
  </div>
</template>

<script>
import axios from 'axios';
import Plotly from 'plotly.js-dist';

export default {
  name: 'App',
  data() {
    return {
      bucketName: '',
      prefix: '',
      maxFiles: 100,
      query: '',
      result: null,
      error: null,
      loading: false,
      filesList: []
    }
  },
  methods: {
    formatSize(bytes) {
      const units = ['B', 'KB', 'MB', 'GB'];
      let size = bytes;
      let unitIndex = 0;
      
      while (size >= 1024 && unitIndex < units.length - 1) {
        size /= 1024;
        unitIndex++;
      }
      
      return `${size.toFixed(1)} ${units[unitIndex]}`;
    },
    
    async listFiles() {
      this.error = null;
      this.loading = true;
      this.filesList = [];
      
      try {
        const response = await axios.get(`http://localhost:55317/list_files`, {
          params: {
            bucket_name: this.bucketName,
            prefix: this.prefix
          }
        });
        
        this.filesList = response.data.files;
      } catch (err) {
        this.error = err.response?.data?.detail || 'An error occurred while listing files';
      } finally {
        this.loading = false;
      }
    },
    
    async analyzeData() {
      this.loading = true;
      this.error = null;
      this.result = null;

      try {
        const response = await axios.post('http://localhost:55317/analyze', {
          bucket_name: this.bucketName,
          prefix: this.prefix,
          max_files: this.maxFiles,
          query: this.query
        });

        this.result = response.data;
        
        // If visualization data is available, render it
        if (this.result.visualization) {
          this.$nextTick(() => {
            Plotly.newPlot(
              this.$refs.plotDiv,
              this.result.visualization.data,
              this.result.visualization.layout
            );
          });
        }
      } catch (err) {
        this.error = err.response?.data?.detail || 'An error occurred while analyzing the data';
      } finally {
        this.loading = false;
      }
    }
  }
}
</script>

<style>
#app {
  font-family: Arial, sans-serif;
  max-width: 800px;
  margin: 0 auto;
  padding: 20px;
}

.input-container {
  margin: 20px 0;
  padding: 20px;
  border: 1px solid #ddd;
  border-radius: 5px;
}

.input-group {
  margin-bottom: 15px;
}

label {
  display: block;
  margin-bottom: 5px;
  font-weight: bold;
}

input, textarea {
  width: 100%;
  padding: 8px;
  border: 1px solid #ddd;
  border-radius: 4px;
  box-sizing: border-box;
}

button {
  background-color: #4CAF50;
  color: white;
  padding: 10px 20px;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  margin-right: 10px;
  margin-bottom: 10px;
}

button:disabled {
  background-color: #cccccc;
  cursor: not-allowed;
}

.error {
  color: red;
  margin: 10px 0;
  padding: 10px;
  border: 1px solid red;
  border-radius: 4px;
}

.result {
  margin-top: 20px;
  padding: 20px;
  border: 1px solid #ddd;
  border-radius: 5px;
}

.visualization {
  margin-top: 20px;
  min-height: 400px;
}

.files-list {
  margin: 15px 0;
  padding: 15px;
  background-color: #f5f5f5;
  border-radius: 4px;
}

.files-list ul {
  max-height: 200px;
  overflow-y: auto;
  padding-left: 20px;
}

.files-list li {
  margin: 5px 0;
  font-family: monospace;
}

.stats {
  color: #666;
  font-style: italic;
}
</style>