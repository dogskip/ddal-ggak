const http = require('node:http');
const fs = require('node:fs');
const { label } = require('./label.cjs');

http.createServer((request, response) => {
  const value = label(request.url === '/preserve' ? '' : ' Hello World ');
  response.setHeader('Content-Type', 'text/html; charset=utf-8');
  response.end(fs.readFileSync('page.html', 'utf8').replace('{{value}}', value));
}).listen(Number(process.argv[2]), '127.0.0.1');
