
const http = require('http');
const fs = require('fs');
const path = require('path');
const url = require('url');

const PORT = 3000;
const BACKEND_PORT = 8000;
const DIST_DIR = path.join(__dirname, 'dist');

const getMimeType = (filePath) => {
    const ext = path.extname(filePath).toLowerCase();
    const types = {
        '.html': 'text/html',
        '.js': 'text/javascript',
        '.css': 'text/css',
        '.json': 'application/json',
        '.png': 'image/png',
        '.jpg': 'image/jpg',
        '.svg': 'image/svg+xml',
    };
    return types[ext] || 'application/octet-stream';
};

const server = http.createServer((req, res) => {
    console.log(`${req.method} ${req.url}`);

    // Proxy API requests
    if (req.url.startsWith('/api/v1')) {
        const options = {
            hostname: '127.0.0.1',
            port: BACKEND_PORT,
            path: req.url,
            method: req.method,
            headers: req.headers,
        };

        const proxyReq = http.request(options, (proxyRes) => {
            res.writeHead(proxyRes.statusCode, proxyRes.headers);
            proxyRes.pipe(res);
        });

        proxyReq.on('error', (e) => {
            console.error(`Proxy Error: ${e.message}`);
            res.writeHead(502);
            res.end('Bad Gateway');
        });

        req.pipe(proxyReq);
        return;
    }

    // Serve Static Files
    let filePath = path.join(DIST_DIR, req.url === '/' ? 'index.html' : req.url);

    // SPA Fallback: If file doesn't exist and not an asset, serve index.html
    if (!fs.existsSync(filePath)) {
        if (!req.url.includes('.')) {
            filePath = path.join(DIST_DIR, 'index.html');
        }
    }

    fs.readFile(filePath, (err, content) => {
        if (err) {
            if (err.code === 'ENOENT') {
                res.writeHead(404);
                res.end('Not Found');
            } else {
                res.writeHead(500);
                res.end('Server Error');
            }
        } else {
            res.writeHead(200, { 'Content-Type': getMimeType(filePath) });
            res.end(content, 'utf-8');
        }
    });
});

server.listen(PORT, '127.0.0.1', () => {
    console.log(`Server running at http://127.0.0.1:${PORT}/`);
});
