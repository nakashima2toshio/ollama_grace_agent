-- init-data/postgres-init.sql
-- 顧客テーブル
CREATE TABLE customers (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    email VARCHAR(100) UNIQUE NOT NULL,
    age INTEGER,
    city VARCHAR(50),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 注文テーブル
CREATE TABLE orders (
    id SERIAL PRIMARY KEY,
    customer_id INTEGER REFERENCES customers(id),
    product_name VARCHAR(100) NOT NULL,
    price DECIMAL(10,2) NOT NULL,
    quantity INTEGER NOT NULL,
    order_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 商品テーブル
CREATE TABLE products (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    category VARCHAR(50),
    price DECIMAL(10,2) NOT NULL,
    stock_quantity INTEGER DEFAULT 0,
    description TEXT
);

-- テストデータ投入
INSERT INTO customers (name, email, age, city) VALUES
('田中太郎', 'tanaka@example.com', 35, '東京'),
('佐藤花子', 'sato@example.com', 28, '大阪'),
('鈴木一郎', 'suzuki@example.com', 42, '名古屋'),
('高橋美香', 'takahashi@example.com', 31, '福岡'),
('渡辺健一', 'watanabe@example.com', 29, '札幌');

INSERT INTO products (name, category, price, stock_quantity, description) VALUES
('ノートPC', 'エレクトロニクス', 89800.00, 15, '高性能ノートパソコン'),
('ワイヤレスイヤホン', 'エレクトロニクス', 12800.00, 25, 'ノイズキャンセリング機能付き'),
('コーヒーメーカー', 'キッチン家電', 15600.00, 10, '全自動コーヒーメーカー'),
('ビジネスバッグ', 'ファッション', 8900.00, 20, 'レザー製ビジネスバッグ'),
('スニーカー', 'ファッション', 9800.00, 30, 'ランニングシューズ');

INSERT INTO orders (customer_id, product_name, price, quantity) VALUES
(1, 'ノートPC', 89800.00, 1),
(2, 'ワイヤレスイヤホン', 12800.00, 2),
(3, 'コーヒーメーカー', 15600.00, 1),
(1, 'ビジネスバッグ', 8900.00, 1),
(4, 'スニーカー', 9800.00, 1),
(5, 'ワイヤレスイヤホン', 12800.00, 1),
(2, 'コーヒーメーカー', 15600.00, 1);