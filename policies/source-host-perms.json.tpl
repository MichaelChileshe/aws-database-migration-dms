{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ReadTheMigrationPasswordsOnly",
      "Effect": "Allow",
      "Action": "secretsmanager:GetSecretValue",
      "Resource": "@@SECRET_ARN@@"
    }
  ]
}
