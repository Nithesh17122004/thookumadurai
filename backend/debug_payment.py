from api.v1.payments import _use_mock_mode, PAYMENT_MOCK_MODE, INSTAMOJO_API_KEY
print(f'PAYMENT_MOCK_MODE constant: {PAYMENT_MOCK_MODE}')
print(f'_use_mock_mode(): {_use_mock_mode()}')
print(f'API_KEY starts with: {INSTAMOJO_API_KEY[:20] if INSTAMOJO_API_KEY else "EMPTY"}')
