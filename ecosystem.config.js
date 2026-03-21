module.exports = {
  apps: [
    {
      name: 'umapyoi-system',
      script: 'run.py',
      interpreter: 'python',
      autorestart: true,
      watch: false,
      max_memory_restart: '1G',
      env: {
        NODE_ENV: 'production',
        PORT: 5000
      }
    }
  ]
};
