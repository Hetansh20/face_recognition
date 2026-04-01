import traceback
from insightface.app import FaceAnalysis

print("Loading FaceAnalysis...")
try:
    app = FaceAnalysis(name='buffalo_l')
    app.prepare(ctx_id=-1)
    print("Success")
except Exception as e:
    print("Caught Exception:")
    traceback.print_exc()
