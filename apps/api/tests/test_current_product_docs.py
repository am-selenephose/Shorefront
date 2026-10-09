from pathlib import Path


def test_current_product_documents_use_only_the_current_identity():
    root = Path(__file__).resolve().parents[3]
    for name in ['README.md', 'brand.md', 'docs/NEXT.md', 'docs/ARCHITECTURE.md']:
        content = (root / name).read_text().lower()
        assert 'kratia' not in content, name
        assert 'portflow' not in content, name
