output "cluster_name" { value = aws_ecs_cluster.main.name }
output "cluster_arn" { value = aws_ecs_cluster.main.arn }
output "service_name" { value = aws_pipes_pipe.sqs_to_fargate.name }
output "task_definition_arn" { value = aws_ecs_task_definition.scanner.arn }
