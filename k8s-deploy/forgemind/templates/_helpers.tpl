{{/*
Application name
*/}}
{{- define "forgemind.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Full application name
*/}}
{{- define "forgemind.fullname" -}}
{{- default .Release.Name .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels
*/}}
{{- define "forgemind.labels" -}}
app.kubernetes.io/name: {{ include "forgemind.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{/*
Selector labels
*/}}
{{- define "forgemind.selectorLabels" -}}
app.kubernetes.io/name: {{ include "forgemind.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
.env file content
*/}}
{{- define "forgemind.envContent" -}}
{{- $first := true -}}
{{- range $key, $val := .Values.env -}}
{{- if not $first -}}{{- "\n" -}}{{- end -}}
{{- $first = false -}}
{{ $key }}={{ $val }}
{{- end -}}
{{- end -}}
