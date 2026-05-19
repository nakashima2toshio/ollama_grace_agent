---
dataset_info:
- config_name: default
  features:
  - name: text
    dtype: string
  - name: id
    dtype: string
  - name: dump
    dtype: string
  - name: url
    dtype: string
  - name: date
    dtype: string
  - name: file_path
    dtype: string
  - name: language
    dtype: string
  - name: language_score
    dtype: float64
  - name: language_script
    dtype: string
  - name: minhash_cluster_size
    dtype: int64
  - name: top_langs
    dtype: string
  - name: score
    dtype: float64
  - name: token_count
    dtype: int64
  splits:
  - name: train
    num_bytes: 619265264278
    num_examples: 120457229
  - name: test
    num_bytes: 40181573
    num_examples: 7720
  download_size: 326618761483
  dataset_size: 619305445851
- config_name: sample_10BT
  features:
  - name: text
    dtype: string
  - name: id
    dtype: string
  - name: dump
    dtype: string
  - name: url
    dtype: string
  - name: date
    dtype: string
  - name: file_path
    dtype: string
  - name: language
    dtype: string
  - name: language_score
    dtype: float64
  - name: language_script
    dtype: string
  - name: minhash_cluster_size
    dtype: int64
  - name: top_langs
    dtype: string
  - name: score
    dtype: float64
  - name: token_count
    dtype: int64
  splits:
  - name: train
    num_bytes: 69373131982
    num_examples: 13488028
  - name: test
    num_bytes: 40181573
    num_examples: 7720
  download_size: 37259153578
  dataset_size: 69413313555
- config_name: small_tokens
  features:
  - name: text
    dtype: string
  - name: id
    dtype: string
  - name: dump
    dtype: string
  - name: url
    dtype: string
  - name: date
    dtype: string
  - name: file_path
    dtype: string
  - name: language
    dtype: string
  - name: language_score
    dtype: float64
  - name: language_script
    dtype: string
  - name: minhash_cluster_size
    dtype: int64
  - name: top_langs
    dtype: string
  - name: score
    dtype: float64
  - name: token_count
    dtype: int64
  splits:
  - name: train
    num_bytes: 144004611027
    num_examples: 64149872
  - name: test
    num_bytes: 9085221
    num_examples: 4041
  download_size: 77794780909
  dataset_size: 144013696248
- config_name: small_tokens_cleaned
  features:
  - name: text
    dtype: string
  - name: is_cleaned
    dtype: bool
  - name: id
    dtype: string
  - name: dump
    dtype: string
  - name: url
    dtype: string
  - name: date
    dtype: string
  - name: file_path
    dtype: string
  - name: language
    dtype: string
  - name: language_score
    dtype: float64
  - name: language_script
    dtype: string
  - name: minhash_cluster_size
    dtype: int64
  - name: top_langs
    dtype: string
  - name: score
    dtype: float64
  - name: token_count
    dtype: int64
  splits:
  - name: train
    num_bytes: 141337983537
    num_examples: 64159872
  - name: test
    num_bytes: 17827073
    num_examples: 8082
  download_size: 75983008004
  dataset_size: 141355810610
configs:
- config_name: default
  data_files:
  - split: train
    path: data/train-*
  - split: test
    path: data/test-*
- config_name: sample_10BT
  data_files:
  - split: train
    path: sample_10BT/train-*
  - split: test
    path: sample_10BT/test-*
- config_name: small_tokens
  data_files:
  - split: train
    path: small_tokens/train-*
  - split: test
    path: small_tokens/test-*
- config_name: small_tokens_cleaned
  data_files:
  - split: train
    path: small_tokens_cleaned/train-*
  - split: test
    path: small_tokens_cleaned/test-*
license: odc-by
language:
- ja
size_categories:
- 10B<n<100B
---

# 🍷 FineWeb2 Edu Japanese: High-Quality Educational Japanese Dataset

![FineWeb2 Edu Japanese image](https://huggingface.co/datasets/hotchpotch/fineweb-2-edu-japanese/resolve/main/assets/fw2.png)

This dataset consists of 120 million texts (approximately 89.3B tokens) filtered from the 376 million Japanese texts in FineWeb2 that were deemed educational. The following subsets are also provided:

- **default**: Approximately 120M texts (120 million texts) totaling around 89.3B tokens
- **sample_10BT**: A random sample of about 10B tokens from the default dataset
- **small_tokens**: Data composed solely of texts with 512 tokens or fewer
- **small_tokens_cleaned**: Data from small_tokens with Web-specific text noise removed

⚠️ WARNING: We apologize for the inconvenience. Please note that **small_tokens** and **small_tokens_cleaned** have duplicate data in the first ranges 0-9999 and 10000-19999. When using these subsets, please skip the first 10,000 items using something like `ds.select(range(10000, len(ds)))`.

[For the introduction article in Japanese, click here.](https://secon.dev/entry/2025/02/20/100000-fineweb-2-edu-japanese/)


## Background on Dataset Creation

[FineWeb](https://huggingface.co/datasets/HuggingFaceFW/fineweb) (English only) was created for deduplicating web data and extracting high-quality text. In addition, [FineWeb-Edu](https://huggingface.co/datasets/HuggingFaceFW/fineweb-edu) extracts high-quality text for educational purposes, enabling efficient learning with fewer tokens.

FineWeb2, published in December 2024, is a high-quality multilingual dataset (including Japanese). However, as of February 2025, the high educational value "Edu" dataset has not been released. Therefore, this project created and published the [FineWeb2 Edu Japanese dataset](https://huggingface.co/datasets/hotchpotch/fineweb-2-edu-japanese).

## Educational Data Filtering

To build this dataset, we filtered the Japanese texts from FineWeb2 using the model [fineweb-2-edu-japanese-classifier](https://huggingface.co/hotchpotch/fineweb-2-edu-japanese-classifier) to determine educational content. The teacher data for scoring the classifier comes from [fineweb-2-edu-japanese-scores](https://huggingface.co/datasets/hotchpotch/fineweb-2-edu-japanese-scores), evaluated by DeepSeek-API (deepseek-chat). Only texts with a score of 2.5 or higher have been extracted, and the score is recorded in the `score` column.

## Token Count Assignment

Token counts, computed using the tokenizer from [ModernBERT-Ja-130M](https://huggingface.co/sbintuitions/modernbert-ja-130m), are included as the `token_count` column.

## Removal of Web-specific Noise

The Japanese data in FineWeb2 may contain boilerplate or unnecessary noise typical of web content. For example, texts such as:


```
この文章は90日以上更新の無いサイトに表示されています。
ログイン ログアウト

本当に必要な文章以外にも、さまざまなノイズが含まれていることがあります。例えば、この文章もその一例です。本来不要なテキストが入ってしまうことがこのようにあるでしょう。

今なら50%オフ！クリックしてリンク先の商品を表示

とりわけ文章長が短い場合、文章のほとんどがノイズを含む可能性があります。それらを取り除くことで、より高品質の文章を抽出できないかと考えています。

前のページ  次のページ
```


To remove such unnecessary text, we developed the model [fineweb-2-japanese-text-cleaner](https://huggingface.co/hotchpotch/fineweb-2-japanese-text-cleaner). The teacher data for noise detection is provided by [fineweb-2-japanese-noise-spans](https://huggingface.co/datasets/hotchpotch/fineweb-2-japanese-noise-spans), which was created using [cyberagent/DeepSeek-R1-Distill-Qwen-32B-Japanese](https://huggingface.co/cyberagent/DeepSeek-R1-Distill-Qwen-32B-Japanese).

This model detects noise sections as shown below:


```
[NOISE]この文章は90日以上更新の無いサイトに表示されています。[/NOISE]
[NOISE]ログイン[/NOISE] [NOISE]ログアウト[/NOISE]

本当に必要な文章以外にも、さまざまなノイズが含まれていることがあります。例えば、この文章もその一例です。本来不要なテキストが入ってしまうことがこのようにあるでしょう。
[NOISE]
今なら50%オフ！クリックしてリンク先の商品を表示[/NOISE]

とりわけ文章長が短い場合、文章のほとんどがノイズを含む可能性があります。それらを取り除くことで、より高品質の文章を抽出できないかと考えています。

[NOISE]前のページ[/NOISE]  [NOISE]次のページ[/NOISE]
```


The `small_tokens_cleaned` subset in this dataset is derived from `small_tokens` by applying the [fineweb-2-japanese-text-cleaner](https://huggingface.co/hotchpotch/fineweb-2-japanese-text-cleaner) model to remove noise. Note that the raw data used for noise detection is published as [fineweb-2-edu-japanese-noise-detect-raw](https://huggingface.co/datasets/hotchpotch/fineweb-2-edu-japanese-noise-detect-raw).

Please note that because noise detection is not perfect, there is a possibility that parts of valid text may be erroneously removed in some cases.

## Caveats

No comparative experiments have been conducted between the "FineWeb2 Edu Japanese" dataset and the original "FineWeb2" dataset (which did not undergo Edu filtering). Therefore, the actual impact on LLM training performance remains unverified.

Additionally, the classification accuracy for determining whether a text is educational is not perfect, and some texts that are not intended for educational purposes may be included.


## License

This dataset is released under the **Open Data Commons Attribution License (ODC-By) v1.0**, as is the original FineWeb2 dataset. Additionally, its use is subject to the [CommonCrawl Terms of Use](https://commoncrawl.org/terms-of-use).

## Citation Information

```
@software{yuichi2025fineweb-2-edu-japanese,
  author = {Yuichi Tateno},
  title = {FineWeb2 Edu Japanese},
  month = feb,
  year = 2025,
  url = {https://huggingface.co/datasets/hotchpotch/fineweb-2-edu-japanese/}
}
```