"""
inference_utils.py

WAJIB digunakan SEBELUM memanggil joblib.load() pada tfidf_vectorizer_v1.pkl.
Alasan: TfidfVectorizer disimpan dengan referensi ke fungsi tokenizer/preprocessor
kustom (identity_tokenizer, identity_preprocessor) yang didefinisikan di top-level
notebook Colab saat training — yang oleh Python dianggap sebagai modul __main__.
joblib/pickle menyimpan REFERENSI (modul + nama fungsi), bukan isi fungsi. Saat
di-load di proses lain (mis. FastAPI), pickle akan mencari fungsi tsb PERSIS di
modul __main__ milik proses baru itu.

Akibatnya, sekadar meng-import fungsi dari file ini TIDAK CUKUP — Anda harus
menempelkannya secara eksplisit ke modul __main__ SEBELUM joblib.load() dipanggil,
atau loading akan tetap gagal dengan:

    AttributeError: Can't get attribute 'identity_preprocessor' on <module '__main__'>

Cara pakai yang BENAR di backend FastAPI (lihat juga contoh nyata di main.py):

    import __main__
    from inference_utils import identity_tokenizer, identity_preprocessor
    __main__.identity_tokenizer = identity_tokenizer
    __main__.identity_preprocessor = identity_preprocessor

    import joblib
    vectorizer = joblib.load("models/tfidf_vectorizer_v1.pkl")
    model = joblib.load("models/sentiment_model_v1.pkl")

Sudah diuji berjalan dengan artefak model_version=v1 (lihat main.py sebagai referensi).
"""


def identity_tokenizer(tokens):
    """review_tokens sudah bersih & ter-tokenisasi — vectorizer tidak perlu memproses ulang."""
    return tokens


def identity_preprocessor(x):
    """No-op preprocessor (fungsi bernama, bukan lambda, agar bisa di-pickle/unpickle)."""
    return x
