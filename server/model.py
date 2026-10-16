"""A budgeted Pydantic-AI model: no provider request bypasses the graph gate."""
import asyncio
from pydantic_ai.models.wrapper import WrapperModel
from server.context import get_context
from server.safety import reserve,settle,rates_for,usage_cost,BudgetExceeded,model_gate
class BudgetedModel(WrapperModel):
    async def request(self,messages,model_settings,model_request_parameters):
        ctx=get_context()
        import copy
        def strict_schema(schema):
            if isinstance(schema,list):return [strict_schema(x) for x in schema]
            if not isinstance(schema,dict):return schema
            schema={k:strict_schema(v) for k,v in schema.items() if k not in {'default','minimum','maximum','minLength','maxLength','minItems','maxItems','pattern','title'}}
            if schema.get('type')=='object' and 'properties' in schema:
                # Session time/cursor and nullable advanced fields use trusted
                # server defaults. Anthropic's strict compiler has a global
                # optional/union limit across the entire tool catalogue.
                props={}
                for name,field in schema['properties'].items():
                    branches=field.get('anyOf',[])
                    nullable=any(b.get('type')=='null' for b in branches) or field.get('type')=='null'
                    if nullable and name!='scope_id':continue
                    if nullable:
                        field=next(b for b in branches if b.get('type')!='null')
                    props[name]=field
                schema['properties']=props
                schema['required']=list(props)
                schema['additionalProperties']=False
                if 'draft' in schema['properties']:
                    schema['properties']['draft']={'type':'null','description':'Use null. The server renders report drafts from session evidence.'}
            return schema
        for tool in model_request_parameters.function_tools:
            tool.strict=True
            tool.parameters_json_schema=strict_schema(copy.deepcopy(tool.parameters_json_schema))
        if ctx.model_requests>=12:raise BudgetExceeded('model_request_limit')
        await model_gate(ctx.identity.tenant)
        token_usage=await self.wrapped.count_tokens(messages,model_settings,model_request_parameters)
        if ctx.input_tokens+token_usage.input_tokens>60000:raise BudgetExceeded('input_token_limit')
        output_max=min((model_settings or {}).get('max_tokens',1024),6000-ctx.output_tokens)
        if output_max<=0:raise BudgetExceeded('output_token_limit')
        inp,out,cache,creation=rates_for(self.model_name)
        upper=(token_usage.input_tokens*max(inp,creation)+output_max*out)/1e6
        await reserve(ctx.identity.tenant,upper)
        ctx.model_requests+=1
        try:
            response=await self.wrapped.request(messages,dict(model_settings or {},max_tokens=output_max),model_request_parameters)
        except BaseException:
            # Unknown provider completion is charged conservatively; retry cannot
            # make a crashed process reset the graph-backed spend reservation.
            await asyncio.shield(settle(ctx.identity.tenant,upper,upper))
            raise
        await settle(ctx.identity.tenant,upper,usage_cost(self.model_name,response.usage),response.usage)
        return response
