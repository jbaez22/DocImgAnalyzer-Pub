output "function_name" { value = aws_lambda_function.api_v2.function_name }
output "function_arn" { value = aws_lambda_function.api_v2.arn }
output "alias_arn" { value = aws_lambda_alias.v2.arn }
output "alias_invoke_arn" { value = aws_lambda_alias.v2.invoke_arn }
output "authorizer_id" { value = aws_apigatewayv2_authorizer.cognito.id }
