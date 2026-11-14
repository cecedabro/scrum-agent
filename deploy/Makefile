.PHONY: validate
validate:
	kustomize build . | kubeconform -strict -summary -ignore-missing-schemas
