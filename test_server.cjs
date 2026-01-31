
const http = require('http');
const server = http.createServer((req, res) => {
    res.writeHead(200);
    res.end('Node Works!');
});
server.listen(3003, '127.0.0.1', () => {
    console.log('Server running at http://127.0.0.1:3003/');
});
