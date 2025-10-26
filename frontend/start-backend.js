#!/usr/bin/env node

import { spawn } from 'child_process';
import { fileURLToPath } from 'url';
import { dirname, join } from 'path';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

console.log('Starting Backend Server...');

// Get the backend directory
const backendDir = join(__dirname, '..', 'backend');

// Kill any existing backend processes
const pkill = spawn('pkill', ['-f', 'simple_backend.py'], {
  stdio: 'ignore'
});

pkill.on('close', () => {
  // Start the backend
  console.log('Starting backend on port 5001...');
  
  const backend = spawn('python3', ['simple_backend.py'], {
    cwd: backendDir,
    stdio: 'inherit'
  });

  backend.on('error', (err) => {
    console.error('Failed to start backend:', err);
    process.exit(1);
  });

  backend.on('exit', (code) => {
    if (code !== 0 && code !== null) {
      console.error(`Backend exited with code ${code}`);
    }
  });

  // Handle process termination
  process.on('SIGINT', () => {
    console.log('\nStopping backend...');
    backend.kill();
    process.exit(0);
  });

  process.on('SIGTERM', () => {
    console.log('\nStopping backend...');
    backend.kill();
    process.exit(0);
  });
});
