class AssuranceError(ValueError):
    def __init__(self, code, field=None, details=None, status='HOLD'):
        self.code, self.field, self.details, self.status = code, field, details, status
        super().__init__(code)

    def as_dict(self):
        return {'status': self.status, 'reason_code': self.code, 'field': self.field,
                'details': self.details, 'execution_permission': False}
