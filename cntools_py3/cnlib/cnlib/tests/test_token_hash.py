from .. import token_hash

def test_hash_token():
    assert token_hash.security_hash_token('cc2d8c377001', \
        'stupidquestionhowtotithelotswife') == '203e278ec7a16e0463b89614e4b5abc3'
    assert token_hash.security_hash_token('cc2d8c376c9c', \
        'stupidquestionhowtotithelotswife') == '59d7f7fa1dbdb03a181864b2ea9cb4b0'
    assert token_hash.security_hash_token('92897baa90070154ba63dd8b3272d3c9e5927850bb9'
        '65f219b748c93288a78c14f384ebfc3c2f56fd9cac5629956124d9ce37c049426af4'
        '2eab555026becc884', 'stupidquestionhowtotithelotswife') == \
        'b0f49815dbfd163e86b81bcedcede0f3'
    assert token_hash.security_hash_token('411457a1c287ab42d61da79c45ff18032d97143cc2e'
        'f57f58d3e00a89486fc974608b7ec3b8ba17d076b4bbcdbcacedc5e6169400ba17b0'
        '63774cc6a36f60408', 'stupidquestionhowtotithelotswife') == \
        '7a9f80e8d651093753843c5c5394d49e'

def test_hash_match():
    assert token_hash.security_hash_match('cc2d8c377001', \
        '203e278ec7a16e0463b89614e4b5abc3', 'stupidquestionhowtotithelotswife')
    assert token_hash.security_hash_match('cc2d8c376c9c', \
        '59d7f7fa1dbdb03a181864b2ea9cb4b0', 'stupidquestionhowtotithelotswife')
    assert token_hash.security_hash_match('92897baa90070154ba63dd8b3272d3c9e5927850bb9'
        '65f219b748c93288a78c14f384ebfc3c2f56fd9cac5629956124d9ce37c049426af4'
        '2eab555026becc884', 'b0f49815dbfd163e86b81bcedcede0f3',
        'stupidquestionhowtotithelotswife')
    assert token_hash.security_hash_match('411457a1c287ab42d61da79c45ff18032d97143cc2e'
        'f57f58d3e00a89486fc974608b7ec3b8ba17d076b4bbcdbcacedc5e6169400ba17b0'
        '63774cc6a36f60408', '7a9f80e8d651093753843c5c5394d49e',
        'stupidquestionhowtotithelotswife')

def test_normalize_mac():
    assert token_hash.normalize_mac('CC:2D:8C:37:70:01') == 'cc2d8c377001'
    assert token_hash.normalize_mac('cc:2d:8c:37:70:01') == 'cc2d8c377001'
    assert token_hash.normalize_mac('cc2d8c377001') == 'cc2d8c377001'
    assert token_hash.normalize_mac('98ac0cb5077945416e81a8b926b17296') == \
        '98ac0cb5077945416e81a8b926b17296'
    assert token_hash.normalize_mac('92897baa90070154ba63dd8b3272d3c9e5927850'
        'bb965f219b748c93288a78c14f384ebfc3c2f56fd9cac5629956124d9ce37c049426'
        'af42eab555026becc884') == '92897baa90070154ba63dd8b3272d3c9e5927850'\
        'bb965f219b748c93288a78c14f384ebfc3c2f56fd9cac5629956124d9ce37c04942'\
        '6af42eab555026becc884'

def test_hash_mac_vizio():
    assert token_hash.hash_mac_vizio('006b9e6a33f6') == \
        '23a353b09517e303ec55ac23ce55de71'
    assert token_hash.hash_mac_vizio('006b9e26e222') == \
        '3cf9fa4d1516d8dbcf100f5218ebf775'

def test_hash_mac_lg():
    assert token_hash.hash_mac_lg('cc2d8c377001') == \
        '92897baa90070154ba63dd8b3272d3c9e5927850bb965f219b748c93288a78c14f3'\
        '84ebfc3c2f56fd9cac5629956124d9ce37c049426af42eab555026becc884'
    assert token_hash.hash_mac_lg('cc2d8c376c9c') == \
        '411457a1c287ab42d61da79c45ff18032d97143cc2ef57f58d3e00a89486fc97460'\
        '8b7ec3b8ba17d076b4bbcdbcacedc5e6169400ba17b063774cc6a36f60408'

def test_hash_mac():
    assert token_hash.hash_mac('006b9e6a33f6', 'VIZIO') == \
        '23a353b09517e303ec55ac23ce55de71'
    assert token_hash.hash_mac('006b9e26e222', 'VIZIO') == \
        '3cf9fa4d1516d8dbcf100f5218ebf775'
    assert token_hash.hash_mac('cc2d8c377001', 'LG') == \
        '92897baa90070154ba63dd8b3272d3c9e5927850bb965f219b748c93288a78c14f3'\
        '84ebfc3c2f56fd9cac5629956124d9ce37c049426af42eab555026becc884'
    assert token_hash.hash_mac('cc2d8c376c9c', 'LG') == \
        '411457a1c287ab42d61da79c45ff18032d97143cc2ef57f58d3e00a89486fc97460'\
        '8b7ec3b8ba17d076b4bbcdbcacedc5e6169400ba17b063774cc6a36f60408'
