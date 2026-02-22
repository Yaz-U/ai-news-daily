<?php
/**
 * AI News Daily - HTMLアップロード受信スクリプト
 * GitHub Actionsからのみ呼び出される想定
 * 設置場所: /www/inc/News/web/upload.php
 */

// 許可トークン（GitHub Secrets の UPLOAD_TOKEN と一致させる）
$SECRET_TOKEN = 'incurator_news_upload_2026_xK9mP3';

// POSTリクエスト以外は拒否
if ($_SERVER['REQUEST_METHOD'] !== 'POST') {
    http_response_code(405);
    die('Method Not Allowed');
}

// トークン認証
$token = $_SERVER['HTTP_X_UPLOAD_TOKEN'] ?? '';
if ($token !== $SECRET_TOKEN) {
    http_response_code(403);
    die('Forbidden: Invalid token');
}

// HTMLコンテンツを取得
$content = file_get_contents('php://input');
if (empty($content)) {
    http_response_code(400);
    die('Bad Request: Empty content');
}

// index.html として保存（自分自身と同じディレクトリ）
$target = __DIR__ . '/index.html';
if (file_put_contents($target, $content) === false) {
    http_response_code(500);
    die('Server Error: Failed to write file');
}

http_response_code(200);
echo 'OK: index.html updated (' . strlen($content) . ' bytes)';
