#!/bin/bash

NAMESPACE=rag
helm uninstall forgemind --namespace $NAMESPACE
