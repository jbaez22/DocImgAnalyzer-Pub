import { Amplify } from 'aws-amplify'

const userPoolId = import.meta.env.VITE_COGNITO_USER_POOL_ID as string
const userPoolClientId = import.meta.env.VITE_COGNITO_CLIENT_ID as string

if (!userPoolId || !userPoolClientId) {
  console.warn('Cognito env vars not set — auth features will not work.')
}

Amplify.configure({
  Auth: {
    Cognito: {
      userPoolId,
      userPoolClientId,
    },
  },
})
