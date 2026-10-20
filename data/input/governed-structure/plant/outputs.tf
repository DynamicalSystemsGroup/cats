output "job_name" {
  value = kubernetes_job_v1.executor.metadata[0].name
}
