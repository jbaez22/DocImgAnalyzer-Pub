# ── VPC ───────────────────────────────────────────────────────────────────────
resource "aws_vpc" "main" {
  cidr_block           = var.vpc_cidr
  enable_dns_hostnames = true
  enable_dns_support   = true

  tags = { Name = "${var.project_name}-${var.environment}-phase2" }
}

# ── Internet Gateway ──────────────────────────────────────────────────────────
resource "aws_internet_gateway" "main" {
  vpc_id = aws_vpc.main.id
  tags   = { Name = "${var.project_name}-${var.environment}-igw" }
}

# ── Public Subnet ─────────────────────────────────────────────────────────────
# Hosts the NAT Gateway and the free S3/DynamoDB Gateway endpoints.
# Lambda and API Gateway are fully managed (not in this VPC).
resource "aws_subnet" "public" {
  vpc_id            = aws_vpc.main.id
  cidr_block        = var.public_subnet_cidr
  availability_zone = var.availability_zone

  tags = { Name = "${var.project_name}-${var.environment}-public-${var.availability_zone}" }
}

# ── Private Subnet ────────────────────────────────────────────────────────────
# Fargate scanner tasks run here. No public IP assigned.
# Outbound internet traffic (ECR pull, Docker Hub, CloudWatch Logs) routes
# through the NAT Gateway in the public subnet.
# count, not a plain resource -- see var.create_private_subnet.
resource "aws_subnet" "private" {
  count             = var.create_private_subnet ? 1 : 0
  vpc_id            = aws_vpc.main.id
  cidr_block        = var.private_subnet_cidr
  availability_zone = var.availability_zone

  tags = { Name = "${var.project_name}-${var.environment}-private-${var.availability_zone}" }
}

# ── Elastic IP for NAT Gateway ────────────────────────────────────────────────
resource "aws_eip" "nat" {
  count  = var.create_private_subnet ? 1 : 0
  domain = "vpc"
  tags   = { Name = "${var.project_name}-${var.environment}-nat-eip" }
}

# ── NAT Gateway ───────────────────────────────────────────────────────────────
# Lives in the PUBLIC subnet. Provides outbound internet for private subnet tasks.
# Replaces three VPC Interface Endpoints (~$43.80/month) at ~$32/month net saving ~$12/month.
resource "aws_nat_gateway" "main" {
  count         = var.create_private_subnet ? 1 : 0
  allocation_id = aws_eip.nat[0].id
  subnet_id     = aws_subnet.public.id

  tags = { Name = "${var.project_name}-${var.environment}-nat" }

  depends_on = [aws_internet_gateway.main]
}

# ── Public Route Table ────────────────────────────────────────────────────────
resource "aws_route_table" "public" {
  vpc_id = aws_vpc.main.id

  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.main.id
  }

  tags = { Name = "${var.project_name}-${var.environment}-public" }
}

resource "aws_route_table_association" "public" {
  subnet_id      = aws_subnet.public.id
  route_table_id = aws_route_table.public.id
}

# ── Private Route Table ───────────────────────────────────────────────────────
resource "aws_route_table" "private" {
  count  = var.create_private_subnet ? 1 : 0
  vpc_id = aws_vpc.main.id

  route {
    cidr_block     = "0.0.0.0/0"
    nat_gateway_id = aws_nat_gateway.main[0].id
  }

  tags = { Name = "${var.project_name}-${var.environment}-private" }
}

resource "aws_route_table_association" "private" {
  count          = var.create_private_subnet ? 1 : 0
  subnet_id      = aws_subnet.private[0].id
  route_table_id = aws_route_table.private[0].id
}

# ── Security Group: Fargate Tasks ─────────────────────────────────────────────
# Tasks have no public IP. Outbound HTTPS covers ECR pulls, Docker Hub (Trivy),
# CloudWatch Logs, and any other AWS API — all routed via the NAT Gateway.
resource "aws_security_group" "fargate_task" {
  name        = "${var.project_name}-${var.environment}-fargate-task"
  description = "Fargate scanner task - outbound HTTPS only"
  vpc_id      = aws_vpc.main.id

  egress {
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

# ── VPC Gateway Endpoints (free — traffic stays on AWS backbone) ──────────────
resource "aws_vpc_endpoint" "s3" {
  vpc_id            = aws_vpc.main.id
  service_name      = "com.amazonaws.${data.aws_region.current.name}.s3"
  vpc_endpoint_type = "Gateway"
  route_table_ids   = concat([aws_route_table.public.id], aws_route_table.private[*].id)

  tags = { Name = "${var.project_name}-${var.environment}-s3" }
}

resource "aws_vpc_endpoint" "dynamodb" {
  vpc_id            = aws_vpc.main.id
  service_name      = "com.amazonaws.${data.aws_region.current.name}.dynamodb"
  vpc_endpoint_type = "Gateway"
  route_table_ids   = concat([aws_route_table.public.id], aws_route_table.private[*].id)

  tags = { Name = "${var.project_name}-${var.environment}-dynamodb" }
}

data "aws_region" "current" {}
