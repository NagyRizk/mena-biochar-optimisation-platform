from .models import MODEL_REGISTRY

def get_model(model_id):
    if model_id not in MODEL_REGISTRY:
        raise KeyError(f"Unknown model id: {model_id}")
    return MODEL_REGISTRY[model_id]

def model_records(model_ids=None):
    ids=model_ids or list(MODEL_REGISTRY)
    return [{"id":i,**MODEL_REGISTRY[i]} for i in ids]
