import torch

class GPUManager:
    _instance = None
    _is_initialized = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(GPUManager, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        if not self._is_initialized:
            self.is_gpu_available = torch.cuda.is_available()
            
            if self.is_gpu_available:
                self.torch_device = "cuda:0"
                self.insightface_ctx_id = 0
                print("\033[92m[GPUManager] ✅ NVIDIA CUDA GPU detected! Hardware acceleration ENABLED.\033[0m")
            else:
                self.torch_device = "cpu"
                self.insightface_ctx_id = -1
                print("\033[93m[GPUManager] ⚠️ No GPU detected. Defaulting to CPU mode. Expect higher CPU usage and latency.\033[0m")
            
            self._is_initialized = True

    def get_torch_device(self):
        return self.torch_device

    def get_insightface_ctx_id(self):
        return self.insightface_ctx_id
