const http = require('node:http');
const fs = require('node:fs');

http.createServer((request, response) => {
  const script = request.url === '/counter.js';
  response.setHeader('Content-Type', script ? 'text/javascript' : 'text/html; charset=utf-8');
  response.end(fs.readFileSync(script ? 'counter.js' : 'index.html'));
}).listen(Number(process.argv[2]), '127.0.0.1');
