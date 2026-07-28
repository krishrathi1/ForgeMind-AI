#!/bin/bash

NAMESPACE=rag
helm uninstall forgemind-dev --namespace $NAMESPACE
