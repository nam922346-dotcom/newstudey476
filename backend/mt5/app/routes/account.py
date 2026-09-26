from flask import Blueprint, jsonify
import MetaTrader5 as mt5
from flasgger import swag_from
import logging

account_bp = Blueprint('account', __name__)
logger = logging.getLogger(__name__)

@account_bp.route('/account_info', methods=['GET'])
@swag_from({
    'tags': ['Account'],
    'responses': {
        200: {
            'description': 'Account info retrieved successfully.',
            'schema': {
                'type': 'object',
                'properties': {
                    'login': {'type': 'integer'},
                    'server': {'type': 'string'},
                    'currency': {'type': 'string'},
                    'leverage': {'type': 'integer'},
                    'balance': {'type': 'number'},
                    'equity': {'type': 'number'},
                    'margin': {'type': 'number'},
                    'free_margin': {'type': 'number'},
                }
            }
        },
        400: {'description': 'Failed to get account info.'},
        500: {'description': 'Internal server error.'}
    }
})
def account_info_endpoint():
    """
    Get Account Information
    ---
    description: Retrieve current trading account details (balance, equity, margin,
                 free margin, currency, leverage, server).
    """
    try:
        info = mt5.account_info()
        if info is None:
            return jsonify({"error": "Failed to get account info"}), 400
        return jsonify(info._asdict())
    except Exception as e:
        logger.error(f"Error in account_info: {str(e)}")
        return jsonify({"error": "Internal server error"}), 500