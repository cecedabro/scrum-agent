.PHONY: validate
validate:
	kustomize build . | kubeconform -strict -summary
