import os


def clean_text_file():
    # ファイルパス設定
    input_path = "./wikipedia_ja_5per_chunks.txt"
    output_path = "./wikipedia_ja_5per_chunks_cleaned.txt"

    # ファイルの存在確認
    if not os.path.exists(input_path):
        print(f"エラー: 入力ファイルが見つかりません: {input_path}")
        return

    print(f"処理開始: {input_path}")
    count_skipped_chunk = 0
    count_skipped_empty = 0
    count_written = 0

    try:
        with open(input_path, 'r', encoding='utf-8') as f_in, \
                open(output_path, 'w', encoding='utf-8') as f_out:

            for line in f_in:
                # 判定用に前後の空白を除去した一時変数を作成
                stripped_line = line.strip()

                # 1. "--- Chunk" で始まる行を削除
                if line.startswith("--- Chunk"):
                    count_skipped_chunk += 1
                    continue

                # 2. 空行（改行のみ、またはスペースのみ）を削除
                if not stripped_line:
                    count_skipped_empty += 1
                    continue

                # 条件を通過した行を書き込む
                f_out.write(line)
                count_written += 1

        print("-" * 30)
        print("処理完了")
        print(f"出力ファイル: {output_path}")
        print(f"削除したChunkヘッダー行: {count_skipped_chunk} 行")
        print(f"削除した空行: {count_skipped_empty} 行")
        print(f"書き込んだ有効行: {count_written} 行")

    except Exception as e:
        print(f"予期せぬエラーが発生しました: {e}")


if __name__ == "__main__":
    clean_text_file()